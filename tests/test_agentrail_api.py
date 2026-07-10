"""
Agent Rail — Phase 2 API tests (+ Phase 3 auth, tests/test_agentrail_auth.py has the
dedicated auth suite; this file's POST /deals calls just need a valid token to reach
the behavior under test).

Negotiation runs as a background asyncio.create_task (see app/agentrail/routes.py),
so these tests use TestClient as a context manager (`with TestClient(app) as client`)
so the portal's event loop keeps the background task alive between requests, and poll
GET /api/agentrail/deals/{id} with short sleeps until the status leaves "negotiating" —
mirroring how the real frontend will observe a live negotiation.

Claude is mocked at the anthropic.AsyncAnthropic class level (not per-instance, since
BuyerAgent/SupplierAgent are constructed inside the route handler and the test has no
handle on them beforehand). Because both agents share the same anthropic module,
one mock client is shared for the two agents; the dispatcher below routes based on
the (distinct) opening line of each agent's system prompt.
"""
import hashlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agentrail import rate_limit
from app.agentrail.routes import AGENTRAIL_DEMO_SUBJECT
from app.offercheck import demo_auth

VALID_SIM_QUOTE = "sim_quote:" + hashlib.sha256(b"agentrail-api-test").hexdigest()


@pytest.fixture(autouse=True)
def _clear_auth_state():
    demo_auth.reset()
    rate_limit.reset()
    yield
    demo_auth.reset()
    rate_limit.reset()


def _auth_headers() -> dict:
    """Mints a fresh, valid demo token — every test in this file needs one to
    get past POST /deals' auth gate; the gate itself is tested in
    tests/test_agentrail_auth.py."""
    token, _ = demo_auth.generate_token(AGENTRAIL_DEMO_SUBJECT, expires_hours=1)
    return {"X-Demo-Token": token}


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _mocked_anthropic(buyer_responses: list[str], supplier_responses: list[str]):
    """Returns a context-manager-ready patch for anthropic.AsyncAnthropic that
    dispatches canned responses based on which agent's system prompt is calling."""
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
        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=dispatch)
        return client

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


def _poll_until_done(client: TestClient, deal_id: str, timeout_s: float = 10.0) -> dict:
    deadline = time.time() + timeout_s
    body = {}
    while time.time() < deadline:
        r = client.get(f"/api/agentrail/deals/{deal_id}")
        body = r.json()
        if body["status"] != "negotiating":
            return body
        time.sleep(0.1)
    raise TimeoutError(f"Deal {deal_id} still negotiating after {timeout_s}s: {body}")


def test_create_deal_returns_negotiating_immediately():
    from app.main import app

    buyer_responses = [json.dumps({
        "action": "propose", "price": 40.0, "quantity": 500,
        "terms": {"ip67_rating": True, "warranty_months": 12}, "reasoning": "Opening.",
    })]
    supplier_responses = [json.dumps({
        "action": "counter", "price": 44.0, "quantity": 500, "terms": {}, "reasoning": "Countering.",
    })]

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock):
        with TestClient(app) as client:
            r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers=_auth_headers())
            assert r.status_code == 201
            body = r.json()
            assert body["status"] == "negotiating"
            assert body["deal_id"]


def test_full_negotiation_reaches_agreement_and_attests():
    from app.main import app

    buyer_responses = [
        json.dumps({"action": "propose", "price": 40.0, "quantity": 500,
                    "terms": {"ip67_rating": True, "warranty_months": 12}, "reasoning": "Opening at $40."}),
        json.dumps({"action": "accept", "price": 41.0, "quantity": 500,
                    "terms": {}, "reasoning": "Accepting supplier's counter."}),
    ]
    supplier_responses = [
        json.dumps({"action": "counter", "price": 41.0, "quantity": 500,
                    "terms": {"ip67_rating": True, "warranty_months": 12, "lead_time_days": 5},
                    "reasoning": "Countering at $41."}),
    ]

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = VALID_SIM_QUOTE

        with TestClient(app) as client:
            r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers=_auth_headers())
            deal_id = r.json()["deal_id"]

            body = _poll_until_done(client, deal_id)
            assert body["status"] == "agreed"
            assert body["final_price"] == 41.0
            assert body["final_quantity"] == 500
            assert body["attestation"] == VALID_SIM_QUOTE
            assert len(body["transcript"]) > 0

            # No sealed value ever appears in the API response.
            body_str = json.dumps(body)
            assert "45.0" not in body_str  # buyer budget_ceiling
            assert "38.0" not in body_str  # supplier floor_price_bulk
            assert "42.0" not in body_str  # supplier floor_price_standard

            r = client.get(f"/api/agentrail/deals/{deal_id}/attest")
            assert r.status_code == 200
            attest = r.json()
            assert attest["valid"] is True
            assert attest["mode"] == "simulation"


def test_negotiation_ends_in_no_deal_on_reject():
    from app.main import app

    buyer_responses = [json.dumps({
        "action": "reject", "price": 0.0, "quantity": 0, "terms": {}, "reasoning": "Not worth it.",
    })]
    supplier_responses = [json.dumps({
        "action": "counter", "price": 44.0, "quantity": 500, "terms": {}, "reasoning": "Countering.",
    })]

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock):
        with TestClient(app) as client:
            r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers=_auth_headers())
            deal_id = r.json()["deal_id"]

            body = _poll_until_done(client, deal_id)
            assert body["status"] == "no_deal"
            assert body["attestation"] is None

            # No attestation available for a deal that never agreed.
            r = client.get(f"/api/agentrail/deals/{deal_id}/attest")
            assert r.status_code == 409


def test_get_unknown_deal_returns_404():
    from app.main import app

    with TestClient(app) as client:
        r = client.get("/api/agentrail/deals/does-not-exist")
        assert r.status_code == 404

        r = client.get("/api/agentrail/deals/does-not-exist/attest")
        assert r.status_code == 404


def test_credential_endpoint_returns_conduct_credential_after_agreement():
    from app.main import app

    buyer_responses = [
        json.dumps({"action": "propose", "price": 40.0, "quantity": 500,
                    "terms": {}, "reasoning": "Opening at $40."}),
        json.dumps({"action": "accept", "price": 41.0, "quantity": 500,
                    "terms": {}, "reasoning": "Accepting supplier's counter."}),
    ]
    supplier_responses = [
        json.dumps({"action": "counter", "price": 41.0, "quantity": 500,
                    "terms": {}, "reasoning": "Countering at $41."}),
    ]

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = VALID_SIM_QUOTE

        with TestClient(app) as client:
            r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers=_auth_headers())
            deal_id = r.json()["deal_id"]
            status_body = _poll_until_done(client, deal_id)
            assert status_body["status"] == "agreed"
            assert status_body["picreds_attested"] is True
            assert status_body["picreds_hash"]

            r = client.get(f"/api/agentrail/deals/{deal_id}/credential")
            assert r.status_code == 200
            cred = r.json()
            assert cred["credential_type"] == "conduct"
            assert cred["genuine_negotiation"] is True
            assert cred["final_price"] == 41.0
            assert cred["picreds_hash"] == status_body["picreds_hash"]
            assert set(cred["checks"].keys()) == {
                "buyer_budget", "seller_floor", "capitulation", "convergence",
            }
            for check in cred["checks"].values():
                assert check["passed"] is True
                assert "$" not in check["finding"]

            # No sealed value anywhere in the credential response.
            cred_str = json.dumps(cred)
            assert "45.0" not in cred_str
            assert "38.0" not in cred_str
            assert "42.0" not in cred_str


def test_credential_endpoint_409_before_agreed():
    from app.main import app

    buyer_responses = [json.dumps({
        "action": "reject", "price": 0.0, "quantity": 0, "terms": {}, "reasoning": "Not worth it.",
    })]
    supplier_responses = [json.dumps({
        "action": "counter", "price": 44.0, "quantity": 500, "terms": {}, "reasoning": "Countering.",
    })]

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock):
        with TestClient(app) as client:
            r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers=_auth_headers())
            deal_id = r.json()["deal_id"]
            _poll_until_done(client, deal_id)

            r = client.get(f"/api/agentrail/deals/{deal_id}/credential")
            assert r.status_code == 409


def test_credential_endpoint_404_unknown_deal():
    from app.main import app

    with TestClient(app) as client:
        r = client.get("/api/agentrail/deals/does-not-exist/credential")
        assert r.status_code == 404


def test_escrow_deposit_and_release_wired_through_deal_lifecycle():
    from app.main import app

    buyer_responses = [json.dumps({
        "action": "propose", "price": 41.0, "quantity": 500, "terms": {}, "reasoning": "Opening.",
    })]
    supplier_responses = [json.dumps({
        "action": "accept", "price": 41.0, "quantity": 500, "terms": {}, "reasoning": "Accepted.",
    })]

    payload = {**_PAYLOAD, "supplier_address": "0x" + "b" * 40, "escrow_amount_eth": 0.05}

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign, \
         patch("app.agentrail.routes.deposit_escrow", new_callable=AsyncMock) as mock_deposit, \
         patch("app.agentrail.routes.release_escrow", new_callable=AsyncMock) as mock_release:
        mock_sign.return_value = VALID_SIM_QUOTE
        mock_deposit.return_value = "0xdeposit123"
        mock_release.return_value = "0xrelease456"

        with TestClient(app) as client:
            r = client.post("/api/agentrail/deals", json=payload, headers=_auth_headers())
            deal_id = r.json()["deal_id"]
            assert mock_deposit.called

            body = _poll_until_done(client, deal_id)
            assert body["status"] == "agreed"
            assert body["escrow_tx"] == "0xdeposit123"
            assert body["settlement_tx"] == "0xrelease456"
            assert mock_release.called


def test_escrow_not_configured_is_non_fatal():
    from app.agentrail.escrow import EscrowNotConfigured
    from app.main import app

    buyer_responses = [json.dumps({
        "action": "propose", "price": 41.0, "quantity": 500, "terms": {}, "reasoning": "Opening.",
    })]
    supplier_responses = [json.dumps({
        "action": "accept", "price": 41.0, "quantity": 500, "terms": {}, "reasoning": "Accepted.",
    })]

    payload = {**_PAYLOAD, "supplier_address": "0x" + "b" * 40, "escrow_amount_eth": 0.05}

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign, \
         patch("app.agentrail.routes.deposit_escrow", new_callable=AsyncMock) as mock_deposit:
        mock_sign.return_value = VALID_SIM_QUOTE
        mock_deposit.side_effect = EscrowNotConfigured("AGENTRAIL_CONTRACT_ADDRESS not set")

        with TestClient(app) as client:
            r = client.post("/api/agentrail/deals", json=payload, headers=_auth_headers())
            assert r.status_code == 201
            deal_id = r.json()["deal_id"]

            body = _poll_until_done(client, deal_id)
            assert body["status"] == "agreed"
            assert body["escrow_tx"] is None
            assert body["settlement_tx"] is None


def test_negotiation_failure_marks_deal_failed_not_500():
    from app.main import app

    buyer_responses = [json.dumps({
        "action": "propose", "price": 40.0, "quantity": 500, "terms": {}, "reasoning": "Opening.",
    })]
    supplier_responses = [json.dumps({
        "action": "accept", "price": 40.0, "quantity": 500, "terms": {}, "reasoning": "Accepted.",
    })]

    with _mocked_anthropic(buyer_responses, supplier_responses), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.side_effect = RuntimeError("tappd unreachable")

        with TestClient(app) as client:
            r = client.post("/api/agentrail/deals", json=_PAYLOAD, headers=_auth_headers())
            assert r.status_code == 201
            deal_id = r.json()["deal_id"]

            body = _poll_until_done(client, deal_id)
            assert body["status"] == "failed"
            assert "tappd unreachable" in body["error"]
