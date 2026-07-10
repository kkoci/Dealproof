"""
Agent Rail — Phase 1 tests.

Mirrors tests/test_negotiation.py's mocking pattern (AsyncMock over
client.messages.create, sign_result patched to avoid hitting tappd) but for
the procurement buyer/supplier flow in app/agentrail/.
"""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _make_agents():
    from app.agentrail.buyer_agent import BuyerAgent
    from app.agentrail.supplier_agent import SupplierAgent

    buyer = BuyerAgent(
        product="industrial sensors",
        quantity=500,
        budget_ceiling=45.0,
        min_spec="IP67 rating, 12-month warranty",
        urgency="moderate — can wait 2 weeks",
    )
    supplier = SupplierAgent(
        product="industrial sensors",
        floor_price_bulk=38.0,
        floor_price_standard=42.0,
        bulk_threshold=200,
        available_inventory=800,
        lead_time_days=5,
    )
    return buyer, supplier


def test_buyer_system_prompt_excludes_supplier_sealed_values():
    buyer, supplier = _make_agents()
    assert "38.0" not in buyer.system_prompt
    assert "42.0" not in buyer.system_prompt
    assert "800" not in buyer.system_prompt  # supplier inventory


def test_supplier_system_prompt_excludes_buyer_sealed_values():
    buyer, supplier = _make_agents()
    assert "45.0" not in supplier.system_prompt  # buyer budget ceiling
    assert "moderate" not in supplier.system_prompt  # buyer urgency


@pytest.mark.asyncio
async def test_negotiation_reaches_agreement_and_attests():
    from app.agentrail.mediator import run_procurement_negotiation

    buyer, supplier = _make_agents()

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

    buyer_calls = {"n": 0}
    supplier_calls = {"n": 0}

    async def buyer_side_effect(*args, **kwargs):
        resp = _mock_response(buyer_responses[buyer_calls["n"] % len(buyer_responses)])
        buyer_calls["n"] += 1
        return resp

    async def supplier_side_effect(*args, **kwargs):
        resp = _mock_response(supplier_responses[supplier_calls["n"] % len(supplier_responses)])
        supplier_calls["n"] += 1
        return resp

    with patch.object(buyer.client.messages, "create", side_effect=buyer_side_effect), \
         patch.object(supplier.client.messages, "create", side_effect=supplier_side_effect), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = "mock-tdx-quote-agentrail"
        result = await run_procurement_negotiation(buyer, supplier, max_rounds=5)

    assert result.agreed is True
    assert result.final_price == 41.0
    assert result.final_quantity == 500
    assert result.attestation == "mock-tdx-quote-agentrail"
    assert len(result.transcript) > 0

    # sign_result was called with a payload — verify no sealed values in it
    call_payload = mock_sign.call_args[0][0]
    payload_str = json.dumps(call_payload)
    assert "45.0" not in payload_str  # buyer budget ceiling
    assert "38.0" not in payload_str  # supplier bulk floor
    assert "42.0" not in payload_str  # supplier standard floor


@pytest.mark.asyncio
async def test_transcript_never_carries_sealed_parameters():
    """Buyer's ceiling and supplier's floors must never appear in the logged
    transcript — the only thing either side or the platform operator sees."""
    from app.agentrail.mediator import run_procurement_negotiation

    buyer, supplier = _make_agents()

    async def buyer_respond(*a, **kw):
        return _mock_response(json.dumps({
            "action": "propose", "price": 40.0, "quantity": 500,
            "terms": {"ip67_rating": True, "warranty_months": 12}, "reasoning": "Opening proposal.",
        }))

    async def supplier_respond(*a, **kw):
        return _mock_response(json.dumps({
            "action": "accept", "price": 40.0, "quantity": 500,
            "terms": {"ip67_rating": True, "warranty_months": 12, "lead_time_days": 5},
            "reasoning": "Accepted.",
        }))

    with patch.object(buyer.client.messages, "create", side_effect=buyer_respond), \
         patch.object(supplier.client.messages, "create", side_effect=supplier_respond), \
         patch("app.agentrail.mediator.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = "mock-tdx-quote"
        result = await run_procurement_negotiation(buyer, supplier, max_rounds=5)

    transcript_str = json.dumps([
        {"terms": r.terms, "reasoning": r.reasoning} for r in result.transcript
    ])
    assert "45.0" not in transcript_str
    assert "38.0" not in transcript_str
    assert "42.0" not in transcript_str


@pytest.mark.asyncio
async def test_negotiation_fails_on_buyer_reject():
    from app.agentrail.mediator import run_procurement_negotiation

    buyer, supplier = _make_agents()

    async def buyer_respond(*a, **kw):
        return _mock_response(json.dumps({
            "action": "reject", "price": 0.0, "quantity": 0, "terms": {}, "reasoning": "Not worth it.",
        }))

    with patch.object(buyer.client.messages, "create", side_effect=buyer_respond):
        result = await run_procurement_negotiation(buyer, supplier, max_rounds=5)

    assert result.agreed is False
    assert result.attestation is None


@pytest.mark.asyncio
async def test_negotiation_fails_after_max_rounds_without_agreement():
    from app.agentrail.mediator import run_procurement_negotiation

    buyer, supplier = _make_agents()

    async def buyer_respond(*a, **kw):
        return _mock_response(json.dumps({
            "action": "counter", "price": 40.0, "quantity": 500, "terms": {}, "reasoning": "Still at $40.",
        }))

    async def supplier_respond(*a, **kw):
        return _mock_response(json.dumps({
            "action": "counter", "price": 44.0, "quantity": 500, "terms": {}, "reasoning": "Still at $44.",
        }))

    with patch.object(buyer.client.messages, "create", side_effect=buyer_respond), \
         patch.object(supplier.client.messages, "create", side_effect=supplier_respond):
        result = await run_procurement_negotiation(buyer, supplier, max_rounds=3)

    assert result.agreed is False
    assert result.attestation is None
    assert len(result.transcript) == 6  # 3 rounds x (buyer + supplier)


def test_verify_quote_simulation_mode():
    from app.agentrail.verify_quote import verify_quote
    import hashlib

    digest = hashlib.sha256(b"x").hexdigest()
    result = verify_quote(f"sim_quote:{digest}")
    assert result["valid"] is True
    assert result["mode"] == "simulation"


def test_verify_quote_rejects_malformed():
    from app.agentrail.verify_quote import verify_quote

    result = verify_quote("sim_quote:not-hex")
    assert result["valid"] is False
