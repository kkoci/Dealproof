"""
Agent Rail — Phase 3 magic-link auth tests.

Mirrors the HTTP e2e section of tests/test_offercheck_demo_auth.py (see that
file on vertical/hr-offer-check), adapted for Agent Rail's simpler model:
no party tokens (no principal/delegation system exists — see CLAUDE.md's
"Still not built" note), and the demo token isn't scoped to a specific deal
(POST /deals is what creates the deal the token would be scoped to).

Covers:
  - POST /deals with no token, an invalid token, or a replayed token -> 401
  - POST /deals with a valid token -> 201, negotiation runs
  - POST /auth/demo-link: X-Internal-Key required, wrong key rejected, valid
    key mints a usable token
  - per-IP rate limit backstop -> 429 (independent of the token check)
  - spend cap surfaces as a "failed" deal, not a crash (background task, so
    it can't become an HTTP 429 the way Offer Check's inline start-agentic can)
  - no sealed value ever appears in a response, auth-gated path included
"""
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agentrail import rate_limit
from app.agentrail.routes import AGENTRAIL_DEMO_SUBJECT
from app.config import settings
from app.offercheck import demo_auth

VALID_SIM_QUOTE = "sim_quote:" + hashlib.sha256(b"agentrail-auth-test").hexdigest()


@pytest.fixture(autouse=True)
def _clear_state():
    demo_auth.reset()
    rate_limit.reset()
    yield
    demo_auth.reset()
    rate_limit.reset()


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _mocked_anthropic(buyer_responses: list[str], supplier_responses: list[str]):
    calls = {"buyer": 0, "supplier": 0}

    async def dispatch(*args, **kwargs):
        system = kwargs.get("system", "")
        if system.startswith("You are a procurement supplier"):
            resp = _mock_response(supplier_responses[calls["supplier"] % len(supplier_responses)])
            calls["supplier"] += 1
        else:
            resp = _mock_response(buyer_responses[calls["buyer"] % len(buyer_responses)])
            calls["buyer"] += 1
        return resp

    def make_client(*args, **kwargs):
        c = MagicMock()
        c.messages.create = AsyncMock(side_effect=dispatch)
        return c

    return patch("anthropic.AsyncAnthropic", side_effect=make_client)


_PAYLOAD = {
    "buyer": {
        "product": "industrial sensors", "quantity": 500, "budget_ceiling": 45.0,
        "min_spec": "IP67 rating, 12-month warranty", "urgency": "moderate",
    },
    "supplier": {
        "product": "industrial sensors", "floor_price_bulk": 38.0, "floor_price_standard": 42.0,
        "bulk_threshold": 200, "available_inventory": 800, "lead_time_days": 5,
    },
    "max_rounds": 5,
}


def _accept_immediately():
    buyer_responses = [json.dumps({
        "action": "propose", "price": 41.0, "quantity": 500, "terms": {}, "reasoning": "Opening.",
    })]
    supplier_responses = [json.dumps({
        "action": "accept", "price": 41.0, "quantity": 500, "terms": {}, "reasoning": "Accepted.",
    })]
    return buyer_responses, supplier_responses


# ---------------------------------------------------------------------------
# POST /deals — auth gate
# ---------------------------------------------------------------------------

def test_create_deal_with_no_token_returns_401(client):
    r = client.post("/api/agentrail/deals", json=_PAYLOAD)
    assert r.status_code == 401


def test_create_deal_with_garbage_token_returns_401(client):
    r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers={"X-Demo-Token": "not-a-real-token"})
    assert r.status_code == 401


def test_create_deal_with_expired_token_returns_401(client):
    token, _ = demo_auth.generate_token(AGENTRAIL_DEMO_SUBJECT, expires_hours=-0.001)
    r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers={"X-Demo-Token": token})
    assert r.status_code == 401


def test_create_deal_with_valid_token_succeeds(client):
    buyer_responses, supplier_responses = _accept_immediately()
    token, _ = demo_auth.generate_token(AGENTRAIL_DEMO_SUBJECT, expires_hours=1)

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = VALID_SIM_QUOTE
        r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers={"X-Demo-Token": token})

    assert r.status_code == 201
    assert r.json()["status"] == "negotiating"


def test_create_deal_token_via_query_param_also_works(client):
    """?token= is accepted alongside X-Demo-Token — for shareable URLs, same
    as Offer Check's start-agentic query_token."""
    buyer_responses, supplier_responses = _accept_immediately()
    token, _ = demo_auth.generate_token(AGENTRAIL_DEMO_SUBJECT, expires_hours=1)

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = VALID_SIM_QUOTE
        r = client.post(f"/api/agentrail/deals?token={token}", json=_PAYLOAD)

    assert r.status_code == 201


def test_replayed_token_returns_401(client):
    buyer_responses, supplier_responses = _accept_immediately()
    token, _ = demo_auth.generate_token(AGENTRAIL_DEMO_SUBJECT, expires_hours=1)

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = VALID_SIM_QUOTE
        first = client.post("/api/agentrail/deals", json=_PAYLOAD, headers={"X-Demo-Token": token})
    assert first.status_code == 201

    second = client.post("/api/agentrail/deals", json=_PAYLOAD, headers={"X-Demo-Token": token})
    assert second.status_code == 401
    assert "already used" in second.json()["detail"]


# ---------------------------------------------------------------------------
# POST /auth/demo-link
# ---------------------------------------------------------------------------

def test_demo_link_requires_internal_key(client):
    r = client.post("/api/agentrail/auth/demo-link", json={})
    assert r.status_code == 401


def test_demo_link_rejects_wrong_internal_key(client):
    r = client.post(
        "/api/agentrail/auth/demo-link", json={}, headers={"X-Internal-Key": "wrong-key"},
    )
    assert r.status_code == 401


def test_demo_link_created_with_valid_internal_key(client):
    r = client.post(
        "/api/agentrail/auth/demo-link",
        json={"expires_hours": 1},
        headers={"X-Internal-Key": settings.offercheck_internal_key},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token"] in body["demo_url"]
    assert "/agent-rail" in body["demo_url"]


def test_demo_link_token_actually_authorizes_deal_creation(client):
    link = client.post(
        "/api/agentrail/auth/demo-link",
        json={},
        headers={"X-Internal-Key": settings.offercheck_internal_key},
    )
    token = link.json()["token"]

    buyer_responses, supplier_responses = _accept_immediately()
    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = VALID_SIM_QUOTE
        r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers={"X-Demo-Token": token})
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# Rate limit backstop
# ---------------------------------------------------------------------------

def test_rate_limit_returns_429_after_limit_exceeded(client):
    """generate_token() is deterministic within the same wall-clock second
    (same subject + same integer expires_at -> identical HMAC) — mint each
    loop token at a distinct expires_hours so they don't collide with each
    other and get rejected as replays instead of exercising the rate limit."""
    buyer_responses, supplier_responses = _accept_immediately()

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = VALID_SIM_QUOTE

        for i in range(rate_limit.DEAL_CREATE_LIMIT):
            token, _ = demo_auth.generate_token(AGENTRAIL_DEMO_SUBJECT, expires_hours=1 + i)
            r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers={"X-Demo-Token": token})
            assert r.status_code == 201

        # One more, even with a fresh valid token — rate limit is IP-scoped, not token-scoped.
        token, _ = demo_auth.generate_token(AGENTRAIL_DEMO_SUBJECT, expires_hours=99)
        r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers={"X-Demo-Token": token})
        assert r.status_code == 429


def test_rate_limit_checked_before_auth(client):
    """A caller with no token at all still counts against — and can trip —
    the rate limit; the 429 doesn't require a valid token to trigger."""
    for _ in range(rate_limit.DEAL_CREATE_LIMIT):
        r = client.post("/api/agentrail/deals", json=_PAYLOAD)
        assert r.status_code == 401  # no token — rejected by auth, but still counted

    r = client.post("/api/agentrail/deals", json=_PAYLOAD)
    assert r.status_code == 429


# ---------------------------------------------------------------------------
# Spend cap — surfaces as a failed deal (background task), not a 429
# ---------------------------------------------------------------------------

def test_spend_cap_exceeded_marks_deal_failed_not_crashed(client):
    import time as time_module

    buyer_responses, supplier_responses = _accept_immediately()
    token, _ = demo_auth.generate_token(AGENTRAIL_DEMO_SUBJECT, expires_hours=1)

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.demo_auth.record_and_check_spend",
               side_effect=demo_auth.SpendCapExceeded("cap hit")):
        r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers={"X-Demo-Token": token})
        assert r.status_code == 201
        deal_id = r.json()["deal_id"]

        deadline = time_module.time() + 5.0
        body = {}
        while time_module.time() < deadline:
            body = client.get(f"/api/agentrail/deals/{deal_id}").json()
            if body["status"] != "negotiating":
                break
            time_module.sleep(0.1)

    assert body["status"] == "failed"
    assert "cap hit" in body["error"]


# ---------------------------------------------------------------------------
# demo_auth.record_and_check_spend's `cap` parameter (added for Agent Rail —
# see app/offercheck/demo_auth.py; default preserves Offer Check's own behavior)
# ---------------------------------------------------------------------------

def test_record_and_check_spend_default_cap_matches_offercheck_constant():
    for _ in range(demo_auth.SPEND_CAP_PER_SESSION):
        demo_auth.record_and_check_spend("some-session")  # should not raise
    with pytest.raises(demo_auth.SpendCapExceeded):
        demo_auth.record_and_check_spend("some-session")


def test_record_and_check_spend_custom_cap_overrides_default():
    for _ in range(3):
        demo_auth.record_and_check_spend("deal-1", cap=3)  # should not raise
    with pytest.raises(demo_auth.SpendCapExceeded):
        demo_auth.record_and_check_spend("deal-1", cap=3)


def test_agentrail_mediator_uses_its_own_spend_cap_not_offercheck_cap():
    from app.agentrail.mediator import AGENTRAIL_SPEND_CAP
    assert AGENTRAIL_SPEND_CAP == 10
    assert AGENTRAIL_SPEND_CAP != demo_auth.SPEND_CAP_PER_SESSION


# ---------------------------------------------------------------------------
# No sealed value ever appears, auth-gated path included
# ---------------------------------------------------------------------------

def test_auth_error_responses_never_leak_sealed_values(client):
    r = client.post("/api/agentrail/deals", json=_PAYLOAD)
    assert r.status_code == 401
    assert "45.0" not in json.dumps(r.json())
    assert "38.0" not in json.dumps(r.json())
    assert "42.0" not in json.dumps(r.json())
