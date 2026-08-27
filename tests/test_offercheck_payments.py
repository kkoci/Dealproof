"""
Tests for Offer Check Phase 4 (vertical/hr-offer-check branch): payment gating —
app.offercheck.credits, the auth.py test-mode registration path, and the new
billing.py Stripe Checkout/webhook functions. See tests/test_offercheck.py and
tests/test_offercheck_phase3.py for the base negotiation/attestation/company-auth
coverage this file builds on.

Payment gating itself is OFF by default (settings.offercheck_payment_gating_enabled)
— every test in this file that needs it ON patches that flag explicitly, matching
the rest of this suite's convention for every other *NotConfigured-gated feature.
"""
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.offercheck import auth, billing, credential, credits, negotiation, rate_limit, store, verifier
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


def _plausible_offer(**overrides):
    defaults = dict(
        company="Stripe", role="Senior Software Engineer", base_salary=180_000,
        equity_value=40_000, bonus=15_000, start_date="2026-09-01",
    )
    defaults.update(overrides)
    return CompetingOffer(**defaults)


def _agreed_session(company_id=None):
    consistency = verifier.check_consistency(_plausible_offer(), 185_000)
    session = store.create_session(_plausible_offer(), 185_000, consistency, company_id=company_id)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    assert session.state == "AGREED"
    return session


def _walkaway_session(company_id=None):
    consistency = verifier.check_consistency(_plausible_offer(), 185_000)
    session = store.create_session(_plausible_offer(), 185_000, consistency, company_id=company_id)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="walk", value=None)
    assert session.state == "WALKAWAY"
    return session


# ---------------------------------------------------------------------------
# credits.py — pure, no HTTP
# ---------------------------------------------------------------------------

def test_debit_for_verification_no_company_id():
    session = _agreed_session(company_id=None)
    result = credits.debit_for_verification(session)
    assert result.charged is False
    assert result.reason == "no_company"


def test_debit_for_verification_unknown_company_id():
    session = _agreed_session(company_id="not-a-real-company-id")
    result = credits.debit_for_verification(session)
    assert result.charged is False
    assert result.reason == "no_company"


def test_debit_for_verification_individual_plan_no_balance():
    company, _ = auth.register_company("Acme Corp")
    company.plan = "individual"
    session = _agreed_session(company_id=company.id)
    result = credits.debit_for_verification(session)
    assert result.charged is False
    assert result.reason == "insufficient_credit"
    assert company.credit_balance == 0


def test_debit_for_verification_individual_plan_with_balance_decrements():
    company, _ = auth.register_company("Acme Corp")
    company.plan = "individual"
    credits.grant_credits(company, 3)
    session = _agreed_session(company_id=company.id)
    result = credits.debit_for_verification(session)
    assert result.charged is True
    assert result.reason == "debited"
    assert company.credit_balance == 2


def test_debit_for_verification_unlimited_never_decrements():
    company, _ = auth.register_company("Acme Corp")
    company.plan = "individual"
    credits.grant_unlimited(company)
    session = _agreed_session(company_id=company.id)
    result = credits.debit_for_verification(session)
    assert result.charged is True
    assert result.reason == "unlimited"
    assert company.credit_balance == 0  # never touched


def test_debit_for_verification_flat_rate_plan_never_needs_credit():
    """team/growth/enterprise are flat-monthly — see billing.record_verification_usage's
    own pre-existing docstring. A flat-rate company with zero credit_balance is still
    charged=True; gating them behind a credit balance would double-enforce money
    already collected outside this module."""
    company, _ = auth.register_company("Acme Corp")
    company.plan = "team"
    assert company.credit_balance == 0
    session = _agreed_session(company_id=company.id)
    result = credits.debit_for_verification(session)
    assert result.charged is True
    assert result.reason == "flat_rate_plan"
    assert company.credit_balance == 0


def test_grant_credits_rejects_non_positive_amount():
    company, _ = auth.register_company("Acme Corp")
    with pytest.raises(ValueError):
        credits.grant_credits(company, 0)
    with pytest.raises(ValueError):
        credits.grant_credits(company, -5)


def test_grant_unlimited_sets_flag():
    company, _ = auth.register_company("Acme Corp")
    assert company.is_unlimited is False
    credits.grant_unlimited(company)
    assert company.is_unlimited is True


# ---------------------------------------------------------------------------
# auth.py — test-mode registration
# ---------------------------------------------------------------------------

def test_register_company_test_mode_grants_starter_credits():
    company, raw_key = auth.register_company("Acme Corp", test_mode=True)
    assert raw_key.startswith("oc_test_")
    assert company.is_test_mode is True
    assert company.credit_balance == credits.TEST_STARTER_CREDITS


def test_register_company_live_mode_grants_no_credits():
    company, raw_key = auth.register_company("Acme Corp")
    assert raw_key.startswith("oc_live_")
    assert company.is_test_mode is False
    assert company.credit_balance == 0


def test_register_company_both_prefixes_satisfy_generic_oc_prefix():
    """The frontend's offercheckCheckCompanyKey heuristic only checks startswith('oc_') —
    confirm both new prefixes still satisfy it."""
    _, live_key = auth.register_company("Acme")
    _, test_key = auth.register_company("Acme Test", test_mode=True)
    assert live_key.startswith("oc_")
    assert test_key.startswith("oc_")


# ---------------------------------------------------------------------------
# routes.py::_maybe_attest gating — direct (no HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_maybe_attest_gating_disabled_by_default_attests_with_no_company():
    """The flag defaults to False — confirms the whole rest of this test suite's
    behavior (real attestation with zero company involvement) is the actual default,
    not an artifact of every other test happening to patch something."""
    from app.offercheck.routes import _maybe_attest
    session = _agreed_session(company_id=None)
    await _maybe_attest(session)
    assert session.attestation is not None
    assert session.payment_required is False


@pytest.mark.asyncio
async def test_maybe_attest_gating_enabled_withholds_proof_with_no_company():
    from app.offercheck.routes import _maybe_attest
    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session = _agreed_session(company_id=None)
        await _maybe_attest(session)
    assert session.attestation is None
    assert session.credential is None
    assert session.market_percentile is None
    assert session.payment_required is True


@pytest.mark.asyncio
async def test_maybe_attest_gating_enabled_attests_with_credit():
    from app.offercheck.routes import _maybe_attest
    company, _ = auth.register_company("Acme Corp")
    company.plan = "individual"
    credits.grant_credits(company, 1)
    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session = _agreed_session(company_id=company.id)
        await _maybe_attest(session)
    assert session.attestation is not None
    assert session.credential is not None
    assert session.payment_required is False
    assert company.credit_balance == 0


@pytest.mark.asyncio
async def test_maybe_attest_gating_enabled_applies_to_non_agreed_terminal_states():
    """A WALKAWAY/EXPIRED/etc. session's own attestation (conduct credential + TDX
    quote) is part of the same paid deliverable — gating isn't AGREED-specific."""
    from app.offercheck.routes import _maybe_attest
    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session = _walkaway_session(company_id=None)
        await _maybe_attest(session)
    assert session.attestation is None
    assert session.payment_required is True


@pytest.mark.asyncio
async def test_maybe_attest_retry_after_credit_added_succeeds():
    from app.offercheck.routes import _maybe_attest
    company, _ = auth.register_company("Acme Corp")
    company.plan = "individual"
    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session = _agreed_session(company_id=company.id)
        await _maybe_attest(session)
        assert session.payment_required is True
        assert session.attestation is None

        credits.grant_credits(company, 1)
        await _maybe_attest(session)
    assert session.attestation is not None
    assert session.payment_required is False


# ---------------------------------------------------------------------------
# HTTP e2e
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _submit_and_agree(client) -> tuple[str, str, str]:
    """Full free negotiation to AGREED via HTTP, no company ever involved — the
    common case this whole design is built around. Returns (session_id,
    candidate_token, employer_token)."""
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 0, "bonus": 0, "start_date": "2026-09-01"},
            "candidate_ask": 185000,
        },
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    client.post(f"/api/offercheck/sessions/{session_id}/employer/band",
                json={"employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 195000})
    client.post(f"/api/offercheck/sessions/{session_id}/employer/move",
                json={"token": employer_token, "move": "accept", "value": None})
    client.post(f"/api/offercheck/sessions/{session_id}/candidate/approval",
                json={"token": candidate_token, "decision": "approve"})
    final = client.post(f"/api/offercheck/sessions/{session_id}/employer/approval",
                         json={"token": employer_token, "decision": "approve"})
    assert final.json()["state"] == "AGREED"
    return session_id, candidate_token, employer_token


def test_company_register_test_mode_endpoint(client):
    resp = client.post("/api/offercheck/company/register", json={"name": "Acme Corp", "test_mode": True})
    assert resp.status_code == 201
    body = resp.json()
    assert body["api_key"].startswith("oc_test_")
    assert body["is_test_mode"] is True
    assert body["credit_balance"] == credits.TEST_STARTER_CREDITS


def test_attest_returns_402_when_payment_required(client):
    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session_id, candidate_token, _ = _submit_and_agree(client)
        resp = client.get(f"/api/offercheck/sessions/{session_id}/attest", params={"token": candidate_token})
    assert resp.status_code == 402


def test_attest_returns_409_when_not_yet_terminal_gating_enabled(client):
    """Confirms the 402 vs 409 split is genuinely conditioned on payment_required,
    not just "attestation is None for any reason"."""
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 0, "bonus": 0, "start_date": "2026-09-01"},
            "candidate_ask": 185000,
        },
    )
    body = submit.json()
    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        resp = client.get(f"/api/offercheck/sessions/{body['session_id']}/attest",
                           params={"token": body["candidate_token"]})
    assert resp.status_code == 409


def test_claim_unlocks_proof_for_unattached_session(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp", "test_mode": True})
    api_key = register.json()["api_key"]

    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session_id, _, _ = _submit_and_agree(client)
        claim = client.post(f"/api/offercheck/sessions/{session_id}/claim", headers={"X-API-Key": api_key})
    assert claim.status_code == 200
    body = claim.json()
    assert body["payment_required"] is False
    assert body["attestation"]["attestation"].startswith("sim_quote:")
    assert body["credit_balance"] == credits.TEST_STARTER_CREDITS - 1


def test_claim_reports_still_unpaid_when_company_has_no_credit(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})  # live, 0 credits
    api_key = register.json()["api_key"]

    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session_id, _, _ = _submit_and_agree(client)
        claim = client.post(f"/api/offercheck/sessions/{session_id}/claim", headers={"X-API-Key": api_key})
    assert claim.status_code == 200
    body = claim.json()
    assert body["payment_required"] is True
    assert body["attestation"] is None


def test_claim_rejects_a_different_company_than_already_claimed(client):
    reg_a = client.post("/api/offercheck/company/register", json={"name": "Acme A", "test_mode": True})
    reg_b = client.post("/api/offercheck/company/register", json={"name": "Acme B", "test_mode": True})
    key_a, key_b = reg_a.json()["api_key"], reg_b.json()["api_key"]

    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session_id, _, _ = _submit_and_agree(client)
        first = client.post(f"/api/offercheck/sessions/{session_id}/claim", headers={"X-API-Key": key_a})
        assert first.status_code == 200
        second = client.post(f"/api/offercheck/sessions/{session_id}/claim", headers={"X-API-Key": key_b})
    assert second.status_code == 403


def test_claim_same_company_twice_is_idempotent(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp", "test_mode": True})
    api_key = register.json()["api_key"]

    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session_id, _, _ = _submit_and_agree(client)
        first = client.post(f"/api/offercheck/sessions/{session_id}/claim", headers={"X-API-Key": api_key})
        second = client.post(f"/api/offercheck/sessions/{session_id}/claim", headers={"X-API-Key": api_key})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["attestation"]["attestation"] == second.json()["attestation"]["attestation"]
    # Second call must NOT debit again — _maybe_attest's own attestation-is-not-None
    # idempotency guard short-circuits before any credit check.
    assert second.json()["credit_balance"] == credits.TEST_STARTER_CREDITS - 1


def test_claim_requires_terminal_session(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp", "test_mode": True})
    api_key = register.json()["api_key"]
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 0, "bonus": 0, "start_date": "2026-09-01"},
            "candidate_ask": 185000,
        },
    )
    session_id = submit.json()["session_id"]
    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        resp = client.post(f"/api/offercheck/sessions/{session_id}/claim", headers={"X-API-Key": api_key})
    assert resp.status_code == 409


def test_claim_requires_valid_api_key(client):
    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session_id, _, _ = _submit_and_agree(client)
        resp = client.post(f"/api/offercheck/sessions/{session_id}/claim", headers={"X-API-Key": "not-real"})
    assert resp.status_code == 403


def test_session_view_exposes_payment_required(client):
    with patch("app.offercheck.routes.settings.offercheck_payment_gating_enabled", True):
        session_id, candidate_token, _ = _submit_and_agree(client)
        view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token})
    assert view.json()["payment_required"] is True
    assert view.json()["state"] == "AGREED"  # outcome itself stayed fully visible


# --- credit purchase (Stripe Checkout) -----------------------------------

def test_purchase_credits_returns_503_when_stripe_unconfigured(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    api_key = register.json()["api_key"]
    resp = client.post(
        "/api/offercheck/company/credits/purchase",
        json={"credit_count": 5, "success_url": "https://example.com/ok", "cancel_url": "https://example.com/cancel"},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 503


def test_purchase_credits_requires_api_key(client):
    resp = client.post(
        "/api/offercheck/company/credits/purchase",
        json={"credit_count": 5, "success_url": "https://example.com/ok", "cancel_url": "https://example.com/cancel"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_credit_checkout_session_posts_correct_line_items():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"url": "https://checkout.stripe.com/session123"}
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.offercheck.billing.settings.stripe_api_key", "sk_test_fake"), \
         patch("httpx.AsyncClient", return_value=ctx):
        url = await billing.create_credit_checkout_session("company-123", 10, "https://ok", "https://cancel")

    assert url == "https://checkout.stripe.com/session123"
    _, kwargs = mock_client.post.call_args
    assert kwargs["data"]["client_reference_id"] == "company-123"
    assert kwargs["data"]["metadata[credit_count]"] == "10"  # what the webhook handler actually reads back
    assert kwargs["data"]["line_items[0][quantity]"] == 10
    assert kwargs["data"]["line_items[0][price_data][unit_amount]"] == 2500  # $25 in cents


@pytest.mark.asyncio
async def test_create_credit_checkout_session_raises_when_unconfigured():
    with patch("app.offercheck.billing.settings.stripe_api_key", ""):
        with pytest.raises(billing.StripeNotConfigured):
            await billing.create_credit_checkout_session("company-123", 10, "https://ok", "https://cancel")


def test_create_credit_checkout_session_rejects_non_positive_count():
    with patch("app.offercheck.billing.settings.stripe_api_key", "sk_test_fake"):
        with pytest.raises(ValueError):
            import asyncio
            asyncio.run(billing.create_credit_checkout_session("company-123", 0, "https://ok", "https://cancel"))


# --- Stripe webhook signature -----------------------------------------

def _stripe_signature_header(raw_body: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.".encode() + raw_body
    sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_verify_stripe_webhook_signature_accepts_valid():
    body = b'{"type": "checkout.session.completed"}'
    header = _stripe_signature_header(body, "whsec_test")
    assert billing.verify_stripe_webhook_signature(body, header, "whsec_test") is True


def test_verify_stripe_webhook_signature_rejects_tampered_body():
    body = b'{"type": "checkout.session.completed"}'
    header = _stripe_signature_header(body, "whsec_test")
    assert billing.verify_stripe_webhook_signature(body + b"x", header, "whsec_test") is False


def test_verify_stripe_webhook_signature_rejects_wrong_secret():
    body = b'{"type": "checkout.session.completed"}'
    header = _stripe_signature_header(body, "whsec_test")
    assert billing.verify_stripe_webhook_signature(body, header, "whsec_other") is False


def test_verify_stripe_webhook_signature_rejects_stale_timestamp():
    body = b'{"type": "checkout.session.completed"}'
    stale = int(time.time()) - billing._STRIPE_WEBHOOK_TOLERANCE_SECONDS - 60
    header = _stripe_signature_header(body, "whsec_test", timestamp=stale)
    assert billing.verify_stripe_webhook_signature(body, header, "whsec_test") is False


def test_verify_stripe_webhook_signature_rejects_malformed_header():
    body = b'{"type": "checkout.session.completed"}'
    assert billing.verify_stripe_webhook_signature(body, "not-a-real-header", "whsec_test") is False
    assert billing.verify_stripe_webhook_signature(body, "", "whsec_test") is False


def test_stripe_webhook_route_503_when_unconfigured(client):
    resp = client.post("/api/offercheck/integrations/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "t=1,v1=x"})
    assert resp.status_code == 503


def test_stripe_webhook_route_403_on_invalid_signature(client):
    with patch("app.offercheck.routes.settings.stripe_webhook_secret", "whsec_test"):
        resp = client.post(
            "/api/offercheck/integrations/stripe/webhook",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
        )
    assert resp.status_code == 403


def _real_checkout_completed_payload(company_id: str, credit_count: int | None, *, include_line_items: bool = False) -> dict:
    """
    A checkout.session.completed payload shaped the way Stripe's real webhook
    delivery actually looks — confirmed live against a real Stripe test-mode
    account via `stripe listen` (see the CRITICAL BUG this regression-tests):
    the session object carries metadata (whatever create_credit_checkout_session
    set at creation time) and client_reference_id, but does NOT inline
    line_items by default, and never has a bare top-level "quantity" field --
    that field doesn't exist on a real Checkout Session object at all. The
    original bug shipped because the old test used an idealized payload with a
    top-level "quantity" the real API never sends.
    """
    obj = {"client_reference_id": company_id}
    if credit_count is not None:
        obj["metadata"] = {"credit_count": str(credit_count)}
    if include_line_items:
        obj["line_items"] = {"data": [{"quantity": credit_count}]}
    return {"type": "checkout.session.completed", "data": {"object": obj}}


def test_stripe_webhook_route_credits_balance_on_valid_event(client):
    """Regression test for the CRITICAL credit-count bug: a real Stripe webhook
    payload (metadata present, no line_items inlined) must credit the ACTUAL
    purchased amount, not silently fall back to 1."""
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]

    payload = _real_checkout_completed_payload(company_id, credit_count=7)
    raw_body = json.dumps(payload).encode()
    header = _stripe_signature_header(raw_body, "whsec_test")

    with patch("app.offercheck.routes.settings.stripe_webhook_secret", "whsec_test"):
        resp = client.post(
            "/api/offercheck/integrations/stripe/webhook",
            content=raw_body,
            headers={"Stripe-Signature": header, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["credited"] == 7
    assert auth.get_company(company_id).credit_balance == 7


def test_stripe_webhook_route_credits_balance_correctly_for_a_larger_purchase(client):
    """The exact live-confirmed failure case: $125 for 5 credits must grant 5,
    not silently degrade to 1 the way the old line_items-summing logic did."""
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]

    payload = _real_checkout_completed_payload(company_id, credit_count=5)
    raw_body = json.dumps(payload).encode()
    header = _stripe_signature_header(raw_body, "whsec_test")

    with patch("app.offercheck.routes.settings.stripe_webhook_secret", "whsec_test"):
        resp = client.post(
            "/api/offercheck/integrations/stripe/webhook",
            content=raw_body,
            headers={"Stripe-Signature": header, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["credited"] == 5
    assert auth.get_company(company_id).credit_balance == 5


def test_stripe_webhook_route_ignores_inlined_line_items_uses_metadata_instead(client):
    """Even if a future Stripe API version (or an `expand` param someone adds
    later) DOES inline line_items with a different, wrong quantity, metadata is
    still the source of truth -- guards against re-introducing a
    line_items-reconstruction path that could disagree with what was actually
    charged."""
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]

    payload = _real_checkout_completed_payload(company_id, credit_count=5, include_line_items=True)
    # Deliberately make the (should-be-ignored) line_items disagree with metadata.
    payload["data"]["object"]["line_items"]["data"][0]["quantity"] = 999
    raw_body = json.dumps(payload).encode()
    header = _stripe_signature_header(raw_body, "whsec_test")

    with patch("app.offercheck.routes.settings.stripe_webhook_secret", "whsec_test"):
        resp = client.post(
            "/api/offercheck/integrations/stripe/webhook",
            content=raw_body,
            headers={"Stripe-Signature": header, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["credited"] == 5
    assert auth.get_company(company_id).credit_balance == 5


def test_stripe_webhook_route_falls_back_to_one_credit_when_metadata_missing(client):
    """Belt-and-suspenders path: if metadata is genuinely absent (shouldn't
    happen now that creation always sets it), still grant 1 rather than 0 --
    matches the original fallback's intent, now reached only in a genuinely
    unexpected state (logged at error level in the route, not silently)."""
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]

    payload = _real_checkout_completed_payload(company_id, credit_count=None)
    raw_body = json.dumps(payload).encode()
    header = _stripe_signature_header(raw_body, "whsec_test")

    with patch("app.offercheck.routes.settings.stripe_webhook_secret", "whsec_test"):
        resp = client.post(
            "/api/offercheck/integrations/stripe/webhook",
            content=raw_body,
            headers={"Stripe-Signature": header, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["credited"] == 1
    assert auth.get_company(company_id).credit_balance == 1


def test_stripe_webhook_route_ignores_unknown_company(client):
    payload = _real_checkout_completed_payload("ghost", credit_count=3)
    raw_body = json.dumps(payload).encode()
    header = _stripe_signature_header(raw_body, "whsec_test")
    with patch("app.offercheck.routes.settings.stripe_webhook_secret", "whsec_test"):
        resp = client.post(
            "/api/offercheck/integrations/stripe/webhook",
            content=raw_body,
            headers={"Stripe-Signature": header},
        )
    assert resp.status_code == 200
    assert resp.json()["ignored"] == "unknown company"


def test_stripe_webhook_route_ignores_other_event_types(client):
    payload = {"type": "payment_intent.created", "data": {"object": {}}}
    raw_body = json.dumps(payload).encode()
    header = _stripe_signature_header(raw_body, "whsec_test")
    with patch("app.offercheck.routes.settings.stripe_webhook_secret", "whsec_test"):
        resp = client.post(
            "/api/offercheck/integrations/stripe/webhook",
            content=raw_body,
            headers={"Stripe-Signature": header},
        )
    assert resp.status_code == 200
    assert resp.json()["ignored"] == "payment_intent.created"


# --- operator-only grant endpoint -----------------------------------

def test_grant_credits_route_requires_internal_key(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]
    resp = client.post("/api/offercheck/company/credits/grant", json={"company_id": company_id, "credit_count": 10})
    assert resp.status_code == 401


def test_grant_credits_route_rejects_wrong_internal_key(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]
    with patch("app.offercheck.routes.settings.offercheck_internal_key", "real-secret"):
        resp = client.post(
            "/api/offercheck/company/credits/grant",
            json={"company_id": company_id, "credit_count": 10},
            headers={"X-Internal-Key": "wrong-secret"},
        )
    assert resp.status_code == 401


def test_grant_credits_route_grants_credit_count(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]
    with patch("app.offercheck.routes.settings.offercheck_internal_key", "real-secret"):
        resp = client.post(
            "/api/offercheck/company/credits/grant",
            json={"company_id": company_id, "credit_count": 25},
            headers={"X-Internal-Key": "real-secret"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["credit_balance"] == 25
    assert body["is_unlimited"] is False


def test_grant_credits_route_grants_unlimited(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]
    with patch("app.offercheck.routes.settings.offercheck_internal_key", "real-secret"):
        resp = client.post(
            "/api/offercheck/company/credits/grant",
            json={"company_id": company_id, "unlimited": True},
            headers={"X-Internal-Key": "real-secret"},
        )
    assert resp.status_code == 200
    assert resp.json()["is_unlimited"] is True


def test_grant_credits_route_requires_amount_or_unlimited(client):
    register = client.post("/api/offercheck/company/register", json={"name": "Acme Corp"})
    company_id = register.json()["company_id"]
    with patch("app.offercheck.routes.settings.offercheck_internal_key", "real-secret"):
        resp = client.post(
            "/api/offercheck/company/credits/grant",
            json={"company_id": company_id},
            headers={"X-Internal-Key": "real-secret"},
        )
    assert resp.status_code == 400


def test_grant_credits_route_unknown_company(client):
    with patch("app.offercheck.routes.settings.offercheck_internal_key", "real-secret"):
        resp = client.post(
            "/api/offercheck/company/credits/grant",
            json={"company_id": "not-real", "credit_count": 10},
            headers={"X-Internal-Key": "real-secret"},
        )
    assert resp.status_code == 404
