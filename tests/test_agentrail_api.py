"""
Agent Rail — Phase 2 API tests.

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

from fastapi.testclient import TestClient

VALID_SIM_QUOTE = "sim_quote:" + hashlib.sha256(b"agentrail-api-test").hexdigest()


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
            r = client.post("/api/agentrail/deals", json=_PAYLOAD)
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
            r = client.post("/api/agentrail/deals", json=_PAYLOAD)
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
            r = client.post("/api/agentrail/deals", json=_PAYLOAD)
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
            r = client.post("/api/agentrail/deals", json=_PAYLOAD)
            assert r.status_code == 201
            deal_id = r.json()["deal_id"]

            body = _poll_until_done(client, deal_id)
            assert body["status"] == "failed"
            assert "tappd unreachable" in body["error"]
