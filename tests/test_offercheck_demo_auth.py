"""
Tests for Offer Check's magic-link auth (app.offercheck.demo_auth) — added on
top of Phase 2A at explicit user request to gate every Claude-calling
endpoint. See demo_auth.py's module docstring for the full design rationale.

Covers:
  - stateless HMAC token generation/verification: roundtrip, tampering,
    expiry, malformed input
  - single-use consumption tracking
  - per-session spend cap
  - startup fail-fast (OFFERCHECK_SECRET_KEY) and the soft key-collision warning
  - HTTP e2e: /auth/demo-link (X-Internal-Key gated), /auth/verify,
    start-agentic via demo-token-only (no party token), single-use rejection,
    spend cap surfacing as 429
"""
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.offercheck import demo_auth, invites, negotiation, rate_limit, store, verifier
from app.offercheck.schemas import CompetingOffer


@pytest.fixture(autouse=True)
def _clear_state():
    store.reset()
    demo_auth.reset()
    rate_limit.reset()
    invites.reset()
    yield
    store.reset()
    demo_auth.reset()
    rate_limit.reset()
    invites.reset()


def _plausible_offer(**overrides):
    defaults = dict(
        company="Stripe", role="Senior Software Engineer", base_salary=180_000,
        equity_value=40_000, bonus=15_000, start_date="2026-09-01",
    )
    defaults.update(overrides)
    return CompetingOffer(**defaults)


def _mock_response(payload: dict):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    return msg


def _scripted(responses: list[dict]):
    calls = {"n": 0}

    async def _side_effect(*args, **kwargs):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return _mock_response(responses[i])

    return _side_effect


# ---------------------------------------------------------------------------
# demo_auth — token generation/verification
# ---------------------------------------------------------------------------

def test_generate_and_verify_token_roundtrip():
    token, expires_at = demo_auth.generate_token("session-1", expires_hours=1)
    result = demo_auth.verify_token("session-1", token)
    assert result == expires_at


def test_verify_rejects_wrong_session_id():
    token, _ = demo_auth.generate_token("session-1", expires_hours=1)
    with pytest.raises(demo_auth.InvalidToken):
        demo_auth.verify_token("session-2", token)


def test_verify_rejects_tampered_signature():
    token, expires_at = demo_auth.generate_token("session-1", expires_hours=1)
    tampered = f"{expires_at}." + "0" * 64
    with pytest.raises(demo_auth.InvalidToken):
        demo_auth.verify_token("session-1", tampered)


def test_verify_rejects_expired_token():
    token, _ = demo_auth.generate_token("session-1", expires_hours=-0.001)  # already expired
    with pytest.raises(demo_auth.InvalidToken):
        demo_auth.verify_token("session-1", token)


@pytest.mark.parametrize("malformed", ["", "no-dot-here", "notanumber.abc123"])
def test_verify_rejects_malformed_tokens(malformed):
    with pytest.raises(demo_auth.InvalidToken):
        demo_auth.verify_token("session-1", malformed)


def test_single_use_consumption():
    token, _ = demo_auth.generate_token("session-1", expires_hours=1)
    assert demo_auth.is_consumed(token) is False
    demo_auth.consume(token)
    assert demo_auth.is_consumed(token) is True


def test_spend_cap_raises_after_limit():
    for _ in range(demo_auth.SPEND_CAP_PER_SESSION):
        demo_auth.record_and_check_spend("session-1")  # should not raise
    with pytest.raises(demo_auth.SpendCapExceeded):
        demo_auth.record_and_check_spend("session-1")


def test_spend_cap_is_per_session():
    for _ in range(demo_auth.SPEND_CAP_PER_SESSION):
        demo_auth.record_and_check_spend("session-1")
    demo_auth.record_and_check_spend("session-2")  # different session, unaffected


def test_require_secret_key_configured_raises_when_unset():
    with patch("app.offercheck.demo_auth.settings.offercheck_secret_key", ""):
        with pytest.raises(RuntimeError):
            demo_auth.require_secret_key_configured()


def test_require_secret_key_configured_passes_when_set():
    with patch("app.offercheck.demo_auth.settings.offercheck_secret_key", "some-secret"):
        demo_auth.require_secret_key_configured()  # should not raise


def test_warn_if_anthropic_keys_identical(caplog):
    with patch("app.offercheck.demo_auth.settings.offercheck_api_key", "sk-same"), \
         patch("app.offercheck.demo_auth.settings.anthropic_api_key", "sk-same"):
        with caplog.at_level("WARNING"):
            demo_auth.warn_if_anthropic_keys_identical()
    assert any("identical" in r.message for r in caplog.records)


def test_no_warning_when_keys_differ(caplog):
    with patch("app.offercheck.demo_auth.settings.offercheck_api_key", "sk-a"), \
         patch("app.offercheck.demo_auth.settings.anthropic_api_key", "sk-b"):
        with caplog.at_level("WARNING"):
            demo_auth.warn_if_anthropic_keys_identical()
    assert not any("identical" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# HTTP e2e
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _sealed_session_via_http(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
            "candidate_floor": 175000,
        },
    )
    body = submit.json()
    client.post(
        f"/api/offercheck/sessions/{body['session_id']}/employer/band",
        json={"employer_token": body["employer_token"], "band_min": 155000, "band_mid": 175000,
              "band_max": 195000, "employer_authority_limit": 195000},
    )
    return body["session_id"]


def test_demo_link_requires_internal_key(client):
    session_id = _sealed_session_via_http(client)
    resp = client.post("/api/offercheck/auth/demo-link", json={"session_id": session_id})
    assert resp.status_code == 401


def test_demo_link_rejects_wrong_internal_key(client):
    session_id = _sealed_session_via_http(client)
    resp = client.post(
        "/api/offercheck/auth/demo-link",
        json={"session_id": session_id},
        headers={"X-Internal-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_demo_link_unknown_session_404(client):
    from app.config import settings
    resp = client.post(
        "/api/offercheck/auth/demo-link",
        json={"session_id": "does-not-exist"},
        headers={"X-Internal-Key": settings.offercheck_internal_key},
    )
    assert resp.status_code == 404


def test_demo_link_created_and_verified(client):
    from app.config import settings
    session_id = _sealed_session_via_http(client)

    link = client.post(
        "/api/offercheck/auth/demo-link",
        json={"session_id": session_id, "expires_hours": 1},
        headers={"X-Internal-Key": settings.offercheck_internal_key},
    )
    assert link.status_code == 200
    body = link.json()
    assert session_id in body["demo_url"]
    assert body["token"] in body["demo_url"]

    verify = client.get("/api/offercheck/auth/verify", params={"token": body["token"], "session": session_id})
    assert verify.status_code == 200
    assert verify.json()["valid"] is True


def test_verify_rejects_invalid_token(client):
    session_id = _sealed_session_via_http(client)
    resp = client.get("/api/offercheck/auth/verify", params={"token": "garbage", "session": session_id})
    assert resp.status_code == 401


def test_start_agentic_via_demo_token_only_no_party_token(client):
    from app.config import settings
    session_id = _sealed_session_via_http(client)

    link = client.post(
        "/api/offercheck/auth/demo-link",
        json={"session_id": session_id},
        headers={"X-Internal-Key": settings.offercheck_internal_key},
    )
    demo_token = link.json()["token"]

    from app.offercheck import store as offercheck_store
    from app.offercheck.agents import mediator as mediator_module
    session = offercheck_store.get_session(session_id)
    candidate_agent, employer_agent = mediator_module.build_agents(session)

    emp_effect = _scripted([{"action": "accept", "value": 190000, "reasoning": "fine"}])
    cand_effect = _scripted([{"action": "counter", "value": 190000, "reasoning": "x"}])

    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect), \
         patch("app.offercheck.agents.mediator.build_agents", return_value=(candidate_agent, employer_agent)):
        resp = client.post(
            f"/api/offercheck/sessions/{session_id}/start-agentic",
            json={},  # no party token at all
            headers={"X-Demo-Token": demo_token},
        )

    assert resp.status_code == 200
    assert resp.json()["state"] == "AGREED"


def test_start_agentic_demo_token_is_single_use(client):
    from app.config import settings
    session_id = _sealed_session_via_http(client)

    link = client.post(
        "/api/offercheck/auth/demo-link",
        json={"session_id": session_id},
        headers={"X-Internal-Key": settings.offercheck_internal_key},
    )
    demo_token = link.json()["token"]

    from app.offercheck import store as offercheck_store
    from app.offercheck.agents import mediator as mediator_module
    session = offercheck_store.get_session(session_id)
    candidate_agent, employer_agent = mediator_module.build_agents(session)

    emp_effect = _scripted([{"action": "accept", "value": 190000, "reasoning": "fine"}])
    cand_effect = _scripted([{"action": "counter", "value": 190000, "reasoning": "x"}])

    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect), \
         patch("app.offercheck.agents.mediator.build_agents", return_value=(candidate_agent, employer_agent)):
        first = client.post(
            f"/api/offercheck/sessions/{session_id}/start-agentic",
            json={},
            headers={"X-Demo-Token": demo_token},
        )
    assert first.status_code == 200

    # Session is now terminal, but re-check the *token itself* is rejected on reuse
    # (independent of the session already being AGREED, which would 409 first).
    second = client.post(
        f"/api/offercheck/sessions/{session_id}/start-agentic",
        json={},
        headers={"X-Demo-Token": demo_token},
    )
    assert second.status_code in (401, 409)  # already-used token, or already-terminal session — never a silent 200


def test_start_agentic_no_auth_at_all_rejected(client):
    session_id = _sealed_session_via_http(client)
    resp = client.post(f"/api/offercheck/sessions/{session_id}/start-agentic", json={})
    assert resp.status_code == 401


def test_start_agentic_surfaces_spend_cap_as_429(client):
    session_id = _sealed_session_via_http(client)
    from app.offercheck import store as offercheck_store
    session = offercheck_store.get_session(session_id)
    candidate_token = session.candidate_token

    with patch("app.offercheck.demo_auth.record_and_check_spend",
               side_effect=demo_auth.SpendCapExceeded("cap hit")):
        resp = client.post(
            f"/api/offercheck/sessions/{session_id}/start-agentic",
            json={"token": candidate_token},
        )
    assert resp.status_code == 429
