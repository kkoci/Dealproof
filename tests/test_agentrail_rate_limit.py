"""
Agent Rail — Phase 3 rate limiter unit tests. Mirrors the structure of Offer
Check's test_offercheck_rate_limit.py (see vertical/hr-offer-check), against
app/agentrail/rate_limit.py's own DEAL_CREATE_LIMIT instead of Offer Check's
SESSION_CREATE_LIMIT/AGENTIC_CALL_LIMIT.
"""
import pytest
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.agentrail import rate_limit


@pytest.fixture(autouse=True)
def _clear_state():
    rate_limit.reset()
    yield
    rate_limit.reset()


def _fake_request(ip: str = "1.2.3.4", forwarded_for: str | None = None):
    req = MagicMock()
    req.client.host = ip
    req.headers = {"x-forwarded-for": forwarded_for} if forwarded_for else {}
    return req


def test_client_ip_prefers_x_forwarded_for():
    req = _fake_request(ip="9.9.9.9", forwarded_for="1.1.1.1, 2.2.2.2")
    assert rate_limit.client_ip(req) == "1.1.1.1"


def test_client_ip_falls_back_to_socket_peer():
    req = _fake_request(ip="9.9.9.9")
    assert rate_limit.client_ip(req) == "9.9.9.9"


def test_check_deal_create_allows_up_to_limit():
    req = _fake_request()
    for _ in range(rate_limit.DEAL_CREATE_LIMIT):
        rate_limit.check_deal_create(req)  # should not raise


def test_check_deal_create_raises_429_over_limit():
    req = _fake_request()
    for _ in range(rate_limit.DEAL_CREATE_LIMIT):
        rate_limit.check_deal_create(req)
    with pytest.raises(HTTPException) as exc_info:
        rate_limit.check_deal_create(req)
    assert exc_info.value.status_code == 429


def test_check_deal_create_is_per_ip():
    req_a = _fake_request(ip="1.1.1.1")
    req_b = _fake_request(ip="2.2.2.2")
    for _ in range(rate_limit.DEAL_CREATE_LIMIT):
        rate_limit.check_deal_create(req_a)
    rate_limit.check_deal_create(req_b)  # different IP, unaffected
