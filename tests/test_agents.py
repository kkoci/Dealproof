"""
Unit tests for buyer and seller agents.

Phase 2 update: BuyerAgent and SellerAgent now use anthropic.AsyncAnthropic,
so client.messages.create is a coroutine. All mocks use AsyncMock.
"""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


@pytest.mark.asyncio
async def test_buyer_accept():
    from app.agents.buyer import BuyerAgent

    buyer = BuyerAgent(budget=1000.0, requirements="10GB labelled image dataset")
    offer = {"action": "offer", "price": 800.0, "terms": {"access_scope": "full", "duration_days": 365}}

    with patch.object(buyer.client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = _mock_response(
            json.dumps({"action": "accept", "price": 800.0, "terms": {}, "reasoning": "Within budget."})
        )
        result = await buyer.evaluate_offer(offer, [])

    assert result["action"] == "accept"
    assert result["price"] == 800.0


@pytest.mark.asyncio
async def test_buyer_counter():
    from app.agents.buyer import BuyerAgent

    buyer = BuyerAgent(budget=1000.0, requirements="10GB labelled image dataset")
    offer = {"action": "offer", "price": 1200.0, "terms": {}}

    with patch.object(buyer.client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = _mock_response(
            json.dumps({"action": "counter", "price": 900.0, "terms": {}, "reasoning": "Too expensive."})
        )
        result = await buyer.evaluate_offer(offer, [])

    assert result["action"] == "counter"
    assert result["price"] == 900.0


@pytest.mark.asyncio
async def test_seller_opening_offer():
    from app.agents.seller import SellerAgent

    seller = SellerAgent(floor_price=500.0, data_description="10GB labelled image dataset, curated 2024")

    with patch.object(seller.client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = _mock_response(
            json.dumps({"action": "offer", "price": 700.0, "terms": {"access_scope": "full", "duration_days": 365}, "reasoning": "Opening bid."})
        )
        result = await seller.make_offer([])

    assert result["action"] == "offer"
    assert result["price"] == 700.0
