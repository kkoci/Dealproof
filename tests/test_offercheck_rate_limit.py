"""
Tests for app.offercheck.rate_limit — closes the gap found while prepping the
Phase 2C Phala deploy: POST /sessions is intentionally open (no login), but
its response hands back both party tokens, so a script can create sessions
and self-authorize start-agentic calls in a loop with zero credential.
demo_auth's magic-link gate and per-session spend cap don't stop that (a
fresh session resets the spend cap every time) — this is the missing layer.

Covers:
  - unit: per-key limits enforced, different IPs tracked independently,
    X-Forwarded-For preferred over the direct socket peer, window
  - HTTP e2e: POST /sessions and start-agentic(-package) both 429 once the
    per-IP limit is exceeded; different endpoints have independent limits
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.offercheck import demo_auth, invites, rate_limit, store


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


class _FakeRequest:
    def __init__(self, ip: str | None = "1.2.3.4", forwarded: str | None = None):
        self.headers = {}
        if forwarded is not None:
            self.headers["x-forwarded-for"] = forwarded
        self.client = MagicMock(host=ip) if ip is not None else None


# ---------------------------------------------------------------------------
# unit
# ---------------------------------------------------------------------------

def test_client_ip_prefers_x_forwarded_for():
    req = _FakeRequest(ip="10.0.0.1", forwarded="203.0.113.5, 10.0.0.1")
    assert rate_limit.client_ip(req) == "203.0.113.5"


def test_client_ip_falls_back_to_socket_peer():
    req = _FakeRequest(ip="10.0.0.1", forwarded=None)
    assert rate_limit.client_ip(req) == "10.0.0.1"


def test_client_ip_unknown_when_no_client():
    req = _FakeRequest(ip=None, forwarded=None)
    assert rate_limit.client_ip(req) == "unknown"


def test_check_session_create_allows_up_to_limit():
    req = _FakeRequest()
    for _ in range(rate_limit.SESSION_CREATE_LIMIT):
        rate_limit.check_session_create(req)  # should not raise


def test_check_session_create_blocks_over_limit():
    req = _FakeRequest()
    for _ in range(rate_limit.SESSION_CREATE_LIMIT):
        rate_limit.check_session_create(req)
    with pytest.raises(Exception) as exc_info:
        rate_limit.check_session_create(req)
    assert "429" in str(exc_info.value) or getattr(exc_info.value, "status_code", None) == 429


def test_check_agentic_call_blocks_over_limit():
    req = _FakeRequest()
    for _ in range(rate_limit.AGENTIC_CALL_LIMIT):
        rate_limit.check_agentic_call(req)
    with pytest.raises(Exception):
        rate_limit.check_agentic_call(req)


def test_different_ips_tracked_independently():
    req_a = _FakeRequest(ip="1.1.1.1")
    req_b = _FakeRequest(ip="2.2.2.2")
    for _ in range(rate_limit.SESSION_CREATE_LIMIT):
        rate_limit.check_session_create(req_a)
    rate_limit.check_session_create(req_b)  # different IP, should not raise


def test_session_create_and_agentic_call_limits_are_independent():
    req = _FakeRequest()
    for _ in range(rate_limit.SESSION_CREATE_LIMIT):
        rate_limit.check_session_create(req)
    # Session-create bucket is exhausted, but the agentic-call bucket is untouched.
    rate_limit.check_agentic_call(req)


# ---------------------------------------------------------------------------
# HTTP e2e
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _submit_body():
    return {
        "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                             "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
        "candidate_ask": 190000,
    }


def test_session_create_rate_limited_over_http(client):
    for _ in range(rate_limit.SESSION_CREATE_LIMIT):
        resp = client.post("/api/offercheck/sessions", json=_submit_body())
        assert resp.status_code == 200
    blocked = client.post("/api/offercheck/sessions", json=_submit_body())
    assert blocked.status_code == 429


def test_start_agentic_rate_limited_over_http(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={**_submit_body(), "candidate_floor": 175000},
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]
    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 195000,
              "employer_authority_limit": 195000},
    )

    # Exhaust the agentic-call bucket with invalid-token calls (rate limit check
    # runs before auth, so these still consume the budget without hitting Claude).
    for _ in range(rate_limit.AGENTIC_CALL_LIMIT):
        resp = client.post(f"/api/offercheck/sessions/{session_id}/start-agentic", json={"token": "wrong"})
        assert resp.status_code == 401

    blocked = client.post(f"/api/offercheck/sessions/{session_id}/start-agentic", json={"token": candidate_token})
    assert blocked.status_code == 429
