"""
Tests for Offer Check Phase 3 (vertical/hr-offer-check branch): company auth,
bulk verification, the πCreds-style conduct credential, billing, and ATS
integrations. See build_spec_offer_check.md and tests/test_offercheck.py
(Phase 1/2) for the base negotiation + attestation + PDF-parsing coverage
this file builds on.
"""
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.offercheck import auth, billing, credential, negotiation, rate_limit, store, verifier
from app.offercheck.integrations import _shared, greenhouse, lever, workday
from app.offercheck.schemas import CompetingOffer

pytestmark = []


@pytest.fixture(autouse=True)
def _clear_stores():
    store.reset()
    auth.reset()
    rate_limit.reset()
    yield
    store.reset()
    auth.reset()
    rate_limit.reset()


def _mock_httpx_client(json_response: dict, status_ok: bool = True):
    mock_response = MagicMock()
    mock_response.json.return_value = json_response
    mock_response.raise_for_status = MagicMock() if status_ok else MagicMock(side_effect=Exception("http error"))

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _plausible_offer(**overrides):
    defaults = dict(
        company="Stripe", role="Senior Software Engineer", base_salary=180_000,
        equity_value=40_000, bonus=15_000, start_date="2026-09-01",
    )
    defaults.update(overrides)
    return CompetingOffer(**defaults)


def _agreed_session(candidate_ask=185_000.0, employer_accept=True):
    consistency = verifier.check_consistency(_plausible_offer(), candidate_ask)
    session = store.create_session(_plausible_offer(), candidate_ask, consistency)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    if employer_accept:
        negotiation.apply_move(session, actor="employer", move="accept", value=None)
    return session


# ---------------------------------------------------------------------------
# auth.py
# ---------------------------------------------------------------------------

def test_register_company_returns_raw_key_once():
    company, raw_key = auth.register_company("Acme Corp")
    assert raw_key.startswith("oc_")
    assert company.api_key_hash == hashlib.sha256(raw_key.encode()).hexdigest()
    assert raw_key not in company.__dict__.values()  # never stored raw


def test_get_company_by_api_key_roundtrip():
    company, raw_key = auth.register_company("Acme Corp")
    assert auth.get_company_by_api_key(raw_key).id == company.id
    assert auth.get_company_by_api_key("wrong-key") is None


def test_connect_ats_sets_provider_and_key():
    company, _ = auth.register_company("Acme Corp")
    assert company.ats_provider is None
    auth.connect_ats(company, "greenhouse", "gh_secret_key")
    assert company.ats_provider == "greenhouse"
    assert company.ats_api_key == "gh_secret_key"


def test_record_session_appends_to_company():
    company, _ = auth.register_company("Acme Corp")
    auth.record_session(company, "session-123")
    assert "session-123" in company.session_ids


# ---------------------------------------------------------------------------
# credential.py
# ---------------------------------------------------------------------------

def test_credential_raises_on_non_terminal_session():
    session = _agreed_session(employer_accept=False)  # band set, no move yet — still PENDING_EMPLOYER
    with pytest.raises(ValueError):
        credential.compute_credential(session)


def test_credential_genuine_negotiation_on_clean_convergence():
    session = store.create_session(_plausible_offer(), 185_000.0, verifier.check_consistency(_plausible_offer(), 185_000.0))
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="counter", value=170_000.0)
    negotiation.apply_move(session, actor="candidate", move="counter", value=180_000.0)
    negotiation.apply_move(session, actor="employer", move="counter", value=177_000.0)
    negotiation.apply_move(session, actor="candidate", move="accept", value=None)

    cred = credential.compute_credential(session)
    assert cred.genuine_negotiation is True
    assert cred.issues == []
    assert cred.outcome == "agreed"
    assert cred.round_count == 4
    assert cred.session_id == session.id


def test_credential_detects_capitulation():
    session = store.create_session(_plausible_offer(), 500_000.0, verifier.check_consistency(_plausible_offer(), 500_000.0))
    negotiation.set_employer_band(session, 100_000, 110_000, 120_000)
    negotiation.apply_move(session, actor="employer", move="counter", value=110_000.0)
    # candidate capitulates from 500k to 115k in one round — an 77%+ single-round swing
    negotiation.apply_move(session, actor="candidate", move="counter", value=115_000.0)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)

    cred = credential.compute_credential(session)
    assert cred.genuine_negotiation is False
    assert any("candidate" in issue for issue in cred.issues)


def test_credential_hash_deterministic():
    session = _agreed_session()
    cred_a = credential.compute_credential(session)
    cred_b = credential.compute_credential(session)
    assert cred_a.credential_hash == cred_b.credential_hash

    serialized = str(cred_a)
    assert "Stripe" not in serialized
    assert "185000" not in serialized


# ---------------------------------------------------------------------------
# billing.py
# ---------------------------------------------------------------------------

def test_pricing_for_plan_valid_and_invalid():
    assert billing.pricing_for_plan("individual")["price_usd"] == 25
    assert billing.pricing_for_plan("growth")["billing_period"] == "monthly"
    with pytest.raises(billing.UnknownPlan):
        billing.pricing_for_plan("not-a-plan")


@pytest.mark.parametrize("hires,expected", [(5, "individual"), (50, "team"), (300, "growth"), (1000, "enterprise")])
def test_recommend_plan_boundaries(hires, expected):
    assert billing.recommend_plan(hires) == expected


@pytest.mark.asyncio
async def test_record_verification_usage_raises_when_not_configured():
    with patch("app.offercheck.billing.settings.stripe_api_key", ""):
        with pytest.raises(billing.StripeNotConfigured):
            await billing.record_verification_usage("company-1", "individual")


@pytest.mark.asyncio
async def test_record_verification_usage_flat_rate_plan_skips_stripe_call():
    with patch("app.offercheck.billing.settings.stripe_api_key", "sk_test_fake"):
        result = await billing.record_verification_usage("company-1", "team")
    assert result == "flat_rate_no_charge"


@pytest.mark.asyncio
async def test_record_verification_usage_individual_plan_calls_stripe():
    mock_ctx = _mock_httpx_client({"id": "ii_fake123"})
    with patch("app.offercheck.billing.settings.stripe_api_key", "sk_test_fake"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        result = await billing.record_verification_usage("company-1", "individual")
    assert result == "ii_fake123"


# ---------------------------------------------------------------------------
# integrations
# ---------------------------------------------------------------------------

def test_verify_hmac_signature_accepts_valid_and_rejects_tampered():
    secret = "webhook-secret"
    body = b'{"event": "ping"}'
    valid_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert _shared.verify_hmac_signature(body, valid_sig, secret) is True
    assert _shared.verify_hmac_signature(body, "0" * 64, secret) is False
    assert _shared.verify_hmac_signature(body, "", secret) is False
    assert _shared.verify_hmac_signature(b'{"event": "tampered"}', valid_sig, secret) is False


@pytest.mark.asyncio
async def test_greenhouse_notify_outcome_raises_when_not_configured():
    with pytest.raises(greenhouse.GreenhouseNotConfigured):
        await greenhouse.notify_outcome("", "candidate-ref", "summary text")


@pytest.mark.asyncio
async def test_greenhouse_notify_outcome_posts_note_when_configured():
    mock_ctx = _mock_httpx_client({"id": 999})
    with patch("httpx.AsyncClient", return_value=mock_ctx):
        result = await greenhouse.notify_outcome("gh_key", "candidate-ref", "3-round negotiation, agreed")
    assert result == 999


@pytest.mark.asyncio
async def test_lever_notify_outcome_raises_when_not_configured():
    with pytest.raises(lever.LeverNotConfigured):
        await lever.notify_outcome("", "opportunity-ref", "summary text")


@pytest.mark.asyncio
async def test_lever_notify_outcome_posts_note_when_configured():
    mock_ctx = _mock_httpx_client({"data": {"id": "note_1"}})
    with patch("httpx.AsyncClient", return_value=mock_ctx):
        result = await lever.notify_outcome("lever_token", "opportunity-ref", "3-round negotiation, agreed")
    assert result == "note_1"


@pytest.mark.asyncio
async def test_workday_notify_outcome_always_raises():
    with pytest.raises(workday.WorkdayNotConfigured):
        await workday.notify_outcome("any-key", "any-ref", "summary")


# ---------------------------------------------------------------------------
# HTTP e2e
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_company_register_endpoint(client):
    resp = client.post("/api/offercheck/company/register", json={"name": "Acme Corp", "hires_per_year": 40})
    assert resp.status_code == 201
    body = resp.json()
    assert body["api_key"].startswith("oc_")
    assert body["recommended_plan"] == "team"
    assert body["pricing"]["price_usd"] == 500


def test_ats_connect_requires_api_key(client):
    resp = client.post("/api/offercheck/company/ats-connect", json={"provider": "greenhouse", "api_key": "gh_x"})
    assert resp.status_code == 401

    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    api_key = register.json()["api_key"]
    connected = client.post(
        "/api/offercheck/company/ats-connect",
        json={"provider": "greenhouse", "api_key": "gh_x"},
        headers={"X-API-Key": api_key},
    )
    assert connected.status_code == 200
    assert connected.json() == {"company_id": register.json()["company_id"], "provider": "greenhouse", "connected": True}


def test_submit_session_with_invalid_api_key_rejected(client):
    resp = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 0, "bonus": 0, "start_date": "2026-09-01"},
            "candidate_ask": 185000,
        },
        headers={"X-API-Key": "not-a-real-key"},
    )
    assert resp.status_code == 403


def test_submit_session_with_valid_api_key_appears_in_company_sessions(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    api_key = register.json()["api_key"]

    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 0, "bonus": 0, "start_date": "2026-09-01"},
            "candidate_ask": 185000,
        },
        headers={"X-API-Key": api_key},
    )
    assert submit.status_code == 200
    session_id = submit.json()["session_id"]

    listing = client.get("/api/offercheck/company/sessions", headers={"X-API-Key": api_key})
    assert listing.status_code == 200
    session_ids = [s["session_id"] for s in listing.json()["sessions"]]
    assert session_id in session_ids


def test_company_sessions_requires_auth(client):
    resp = client.get("/api/offercheck/company/sessions")
    assert resp.status_code == 401


def test_bulk_verify_creates_multiple_sessions(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    api_key = register.json()["api_key"]

    bulk = client.post(
        "/api/offercheck/company/verify/bulk",
        json={
            "verifications": [
                {"competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                      "equity_value": 0, "bonus": 0, "start_date": "2026-09-01"},
                 "candidate_ask": 185000},
                {"competing_offer": {"company": "Google", "role": "Engineer", "base_salary": 190000,
                                      "equity_value": 0, "bonus": 0, "start_date": "2026-09-01"},
                 "candidate_ask": 200000},
            ]
        },
        headers={"X-API-Key": api_key},
    )
    assert bulk.status_code == 200
    body = bulk.json()
    assert len(body["results"]) == 2
    assert body["results"][0]["session_id"] != body["results"][1]["session_id"]

    listing = client.get("/api/offercheck/company/sessions", headers={"X-API-Key": api_key})
    assert len(listing.json()["sessions"]) == 2


def test_credential_endpoint_requires_terminal_state(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Meta", "role": "Engineer", "base_salary": 190000,
                                 "equity_value": 0, "bonus": 0, "start_date": "2026-09-01"},
            "candidate_ask": 200000,
        },
    )
    body = submit.json()
    resp = client.get(
        f"/api/offercheck/sessions/{body['session_id']}/credential",
        params={"token": body["candidate_token"]},
    )
    assert resp.status_code == 409


def test_credential_endpoint_via_token_and_via_company_api_key(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    api_key = register.json()["api_key"]

    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Meta", "role": "Engineer", "base_salary": 190000,
                                 "equity_value": 0, "bonus": 0, "start_date": "2026-09-01"},
            "candidate_ask": 200000,
        },
        headers={"X-API-Key": api_key},
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 180000, "band_mid": 195000, "band_max": 210000},
    )
    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "accept", "value": None},
    )

    via_token = client.get(f"/api/offercheck/sessions/{session_id}/credential", params={"token": candidate_token})
    assert via_token.status_code == 200
    assert via_token.json()["genuine_negotiation"] is True
    assert via_token.json()["outcome"] == "agreed"

    via_company = client.get(f"/api/offercheck/sessions/{session_id}/credential", headers={"X-API-Key": api_key})
    assert via_company.status_code == 200
    assert via_company.json()["credential_hash"] == via_token.json()["credential_hash"]

    # Wrong company's key must not work.
    other = client.post("/api/offercheck/company/register", json={"name": "Other Co"})
    other_key = other.json()["api_key"]
    forbidden = client.get(f"/api/offercheck/sessions/{session_id}/credential", headers={"X-API-Key": other_key})
    assert forbidden.status_code == 403

    # The attestation receipt now also carries the credential hash.
    attest = client.get(f"/api/offercheck/sessions/{session_id}/attest", params={"token": candidate_token})
    assert attest.json()["credential_hash"] == via_token.json()["credential_hash"]


def test_ats_webhook_valid_signature_accepted(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id, api_key = register.json()["company_id"], register.json()["api_key"]
    client.post(
        "/api/offercheck/company/ats-connect",
        json={"provider": "greenhouse", "api_key": "gh_key"},
        headers={"X-API-Key": api_key},
    )

    company = auth.get_company(company_id)
    body = b'{"event": "ping"}'
    sig = hmac.new(company.webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    resp = client.post(
        f"/api/offercheck/integrations/greenhouse/webhook/{company_id}",
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json() == {"received": True, "provider": "greenhouse"}


def test_ats_webhook_tampered_signature_rejected(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id, api_key = register.json()["company_id"], register.json()["api_key"]
    client.post(
        "/api/offercheck/company/ats-connect",
        json={"provider": "greenhouse", "api_key": "gh_key"},
        headers={"X-API-Key": api_key},
    )

    resp = client.post(
        f"/api/offercheck/integrations/greenhouse/webhook/{company_id}",
        content=b'{"event": "ping"}',
        headers={"Content-Type": "application/json", "X-Signature": "0" * 64},
    )
    assert resp.status_code == 403


def test_ats_webhook_unconnected_provider_rejected(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]

    resp = client.post(
        f"/api/offercheck/integrations/lever/webhook/{company_id}",
        content=b'{"event": "ping"}',
        headers={"Content-Type": "application/json", "X-Signature": "irrelevant"},
    )
    assert resp.status_code == 400


def test_ats_webhook_unknown_company_404(client):
    resp = client.post(
        "/api/offercheck/integrations/greenhouse/webhook/does-not-exist",
        content=b'{"event": "ping"}',
        headers={"Content-Type": "application/json", "X-Signature": "irrelevant"},
    )
    assert resp.status_code == 404
