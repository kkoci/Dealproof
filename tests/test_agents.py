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


# ---------------------------------------------------------------------------
# AuditorAgent tests
# ---------------------------------------------------------------------------

TRANSCRIPT = [
    {"round": 1, "role": "seller", "action": "offer", "price": 900.0},
    {"round": 1, "role": "buyer", "action": "counter", "price": 650.0},
    {"round": 2, "role": "seller", "action": "counter", "price": 780.0},
    {"round": 2, "role": "buyer", "action": "accept", "price": 780.0},
]

AUDIT_LLM_RESPONSE = {
    "genuine_negotiation": True,
    "summary": "Both parties engaged in genuine back-and-forth converging to a fair price.",
}


@pytest.mark.asyncio
async def test_auditor_produces_valid_report():
    from app.agents.auditor import AuditorAgent

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(json.dumps(AUDIT_LLM_RESPONSE))
        )
        agent = AuditorAgent()
        report = await agent.audit(TRANSCRIPT, buyer_budget=1000.0, floor_price=600.0, final_price=780.0)

    assert report is not None
    assert report.genuine_negotiation is True
    assert report.round_count == 2
    assert report.final_price == 780.0
    assert isinstance(report.summary, str)
    assert len(report.credential_hash) == 64  # SHA-256 hex


@pytest.mark.asyncio
async def test_auditor_raises_on_failure():
    from app.agents.auditor import AuditorAgent

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=Exception("API unavailable"))
        agent = AuditorAgent()
        with pytest.raises(Exception, match="API unavailable"):
            await agent.audit(TRANSCRIPT, buyer_budget=1000.0, floor_price=600.0, final_price=780.0)


@pytest.mark.asyncio
async def test_auditor_credential_hash_changes_with_summary():
    from app.agents.auditor import AuditorAgent

    response_a = {"genuine_negotiation": True, "summary": "Parties reached agreement efficiently."}
    response_b = {"genuine_negotiation": True, "summary": "Protracted negotiation with many concessions."}

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.messages.create = AsyncMock(return_value=_mock_response(json.dumps(response_a)))
        agent = AuditorAgent()
        report_a = await agent.audit(TRANSCRIPT, buyer_budget=1000.0, floor_price=600.0, final_price=780.0)

        mock_client.messages.create = AsyncMock(return_value=_mock_response(json.dumps(response_b)))
        report_b = await agent.audit(TRANSCRIPT, buyer_budget=1000.0, floor_price=600.0, final_price=780.0)

    assert report_a is not None
    assert report_b is not None
    assert report_a.credential_hash != report_b.credential_hash
