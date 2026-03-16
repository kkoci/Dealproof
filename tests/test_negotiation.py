"""
Integration tests for the negotiation loop.

Phase 3 updates:
  - run_negotiation() now accepts optional data_hash parameter; tests cover
    both the with-data_hash (combined attestation) and without-data_hash paths.
  - sign_result is patched in all tests to avoid hitting tappd.
  - AsyncMock used throughout (agents use AsyncAnthropic since Phase 2).
"""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


@pytest.mark.asyncio
async def test_negotiation_reaches_agreement():
    from app.agents.buyer import BuyerAgent
    from app.agents.seller import SellerAgent
    from app.agents.negotiation import run_negotiation

    buyer = BuyerAgent(budget=1000.0, requirements="test data")
    seller = SellerAgent(floor_price=500.0, data_description="test dataset")

    seller_responses = [
        json.dumps({"action": "offer", "price": 700.0, "terms": {}, "reasoning": "Opening."}),
        json.dumps({"action": "accept", "price": 700.0, "terms": {}, "reasoning": "Deal."}),
    ]
    buyer_responses = [
        json.dumps({"action": "counter", "price": 650.0, "terms": {}, "reasoning": "Counter."}),
    ]

    seller_call_count = 0
    buyer_call_count = 0

    async def seller_side_effect(*args, **kwargs):
        nonlocal seller_call_count
        resp = _mock_response(seller_responses[seller_call_count % len(seller_responses)])
        seller_call_count += 1
        return resp

    async def buyer_side_effect(*args, **kwargs):
        nonlocal buyer_call_count
        resp = _mock_response(buyer_responses[buyer_call_count % len(buyer_responses)])
        buyer_call_count += 1
        return resp

    with patch.object(seller.client.messages, "create", side_effect=seller_side_effect), \
         patch.object(buyer.client.messages, "create", side_effect=buyer_side_effect), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = "mock-tdx-quote-abc123"
        result = await run_negotiation(buyer, seller, max_rounds=5)

    assert result.agreed is True
    assert result.final_price is not None
    assert result.attestation == "mock-tdx-quote-abc123"
    assert len(result.transcript) > 0


@pytest.mark.asyncio
async def test_negotiation_with_data_hash_in_attestation():
    """Phase 3: when data_hash is passed, sign_result receives combined payload."""
    from app.agents.buyer import BuyerAgent
    from app.agents.seller import SellerAgent
    from app.agents.negotiation import run_negotiation

    buyer = BuyerAgent(budget=1000.0, requirements="test data")
    seller = SellerAgent(floor_price=500.0, data_description="test dataset")

    async def seller_respond(*a, **kw):
        return _mock_response(
            json.dumps({"action": "offer", "price": 700.0, "terms": {}, "reasoning": ""})
        )

    async def buyer_respond(*a, **kw):
        return _mock_response(
            json.dumps({"action": "accept", "price": 700.0, "terms": {}, "reasoning": ""})
        )

    test_data_hash = "a" * 64

    with patch.object(seller.client.messages, "create", side_effect=seller_respond), \
         patch.object(buyer.client.messages, "create", side_effect=buyer_respond), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = "combined-tdx-quote"
        result = await run_negotiation(buyer, seller, max_rounds=3, data_hash=test_data_hash)

    assert result.agreed is True
    # Verify the sign_result payload included data_hash and data_verified
    call_payload = mock_sign.call_args[0][0]
    assert call_payload["data_hash"] == test_data_hash
    assert call_payload["data_verified"] is True
    assert "final_price" in call_payload
    assert "terms" in call_payload


@pytest.mark.asyncio
async def test_negotiation_without_data_hash_no_data_fields():
    """Without data_hash, sign_result payload must NOT contain data_hash or data_verified."""
    from app.agents.buyer import BuyerAgent
    from app.agents.seller import SellerAgent
    from app.agents.negotiation import run_negotiation

    buyer = BuyerAgent(budget=1000.0, requirements="test data")
    seller = SellerAgent(floor_price=500.0, data_description="test dataset")

    async def seller_respond(*a, **kw):
        return _mock_response(
            json.dumps({"action": "offer", "price": 700.0, "terms": {}, "reasoning": ""})
        )

    async def buyer_respond(*a, **kw):
        return _mock_response(
            json.dumps({"action": "accept", "price": 700.0, "terms": {}, "reasoning": ""})
        )

    with patch.object(seller.client.messages, "create", side_effect=seller_respond), \
         patch.object(buyer.client.messages, "create", side_effect=buyer_respond), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = "deal-only-quote"
        result = await run_negotiation(buyer, seller, max_rounds=3, data_hash=None)

    assert result.agreed is True
    call_payload = mock_sign.call_args[0][0]
    assert "data_hash" not in call_payload
    assert "data_verified" not in call_payload


@pytest.mark.asyncio
async def test_negotiation_fails_on_reject():
    from app.agents.buyer import BuyerAgent
    from app.agents.seller import SellerAgent
    from app.agents.negotiation import run_negotiation

    buyer = BuyerAgent(budget=1000.0, requirements="test data")
    seller = SellerAgent(floor_price=500.0, data_description="test dataset")

    with patch.object(seller.client.messages, "create", new_callable=AsyncMock) as mock_seller, \
         patch.object(buyer.client.messages, "create", new_callable=AsyncMock) as mock_buyer:

        mock_seller.return_value = _mock_response(
            json.dumps({"action": "offer", "price": 800.0, "terms": {}, "reasoning": "Offer."})
        )
        mock_buyer.return_value = _mock_response(
            json.dumps({"action": "reject", "price": 0.0, "terms": {}, "reasoning": "Not interested."})
        )

        result = await run_negotiation(buyer, seller, max_rounds=3)

    assert result.agreed is False
    assert result.attestation is None
