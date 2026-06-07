"""
Tests for app/picreds — πCreds auditor and credential construction.

All Anthropic API calls are mocked; no live inference needed.
"""
import json
import hashlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_anthropic_response(json_payload: dict):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(json_payload))]
    return msg


POLICY_RESPONSE = {
    "claims": ["Never offer above budget", "Start at 60% of budget"],
    "hard_constraints": ["Never offer above budget"],
    "guidelines": ["Start at 60% of budget"],
    "assessment": "A buyer agent constrained to negotiate within budget.",
}

CONDUCT_RESPONSE = {
    "buyer_budget_respected": True,
    "seller_floor_respected": True,
    "no_collusion_detected": True,
    "genuine_negotiation": True,
    "findings": ["Buyer opened at floor, seller accepted in round 1."],
    "assessment": "Both agents complied with their constraints throughout.",
}


# ---------------------------------------------------------------------------
# Auditor tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_agent_policy_ok():
    from app.picreds.auditor import audit_agent_policy

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response(POLICY_RESPONSE))

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await audit_agent_policy("buyer", "You are a buyer. Never exceed budget.")

    assert result["hard_constraints"] == ["Never offer above budget"]
    assert "assessment" in result
    mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_audit_deal_conduct_ok():
    from app.picreds.auditor import audit_deal_conduct

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response(CONDUCT_RESPONSE))

    transcript = [
        {"round": 1, "role": "seller", "action": "offer", "price": 840.0},
        {"round": 1, "role": "buyer", "action": "counter", "price": 600.0},
        {"round": 1, "role": "seller", "action": "accept", "price": 600.0},
    ]

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await audit_deal_conduct(transcript, 1000.0, 600.0, 600.0)

    assert result["buyer_budget_respected"] is True
    assert result["seller_floor_respected"] is True
    assert result["no_collusion_detected"] is True


# ---------------------------------------------------------------------------
# Credential construction tests
# ---------------------------------------------------------------------------

def test_make_credential_structure():
    from app.picreds.credential import make_credential

    cred = make_credential(
        credential_type="policy",
        subject="buyer_agent",
        audit_result=POLICY_RESPONSE,
        deal_id="deal-123",
        code_hash="abc" * 21 + "a",
    )

    assert cred["type"] == "DealProofCredential"
    assert cred["credential_type"] == "policy"
    assert cred["subject"] == "buyer_agent"
    assert cred["deal_id"] == "deal-123"
    assert cred["audit_result"] == POLICY_RESPONSE
    assert isinstance(cred["issued_at"], int)


def test_hash_credentials_deterministic():
    from app.picreds.credential import make_credential, hash_credential, hash_credentials
    import time

    cred1 = make_credential("policy", "buyer_agent", POLICY_RESPONSE, "deal-1", "h1")
    cred2 = make_credential("conduct", "deal", CONDUCT_RESPONSE, "deal-1", "")

    h1 = hash_credentials([cred1, cred2])
    h2 = hash_credentials([cred2, cred1])  # order shouldn't matter (sorted internally)

    assert len(h1) == 64
    assert h1 == h2


def test_individual_credential_hash_is_sha256():
    from app.picreds.credential import make_credential, hash_credential

    cred = make_credential("conduct", "deal", CONDUCT_RESPONSE, "deal-1", "")
    h = hash_credential(cred)

    expected = hashlib.sha256(json.dumps(cred, sort_keys=True).encode()).hexdigest()
    assert h == expected


# ---------------------------------------------------------------------------
# Integration: πCreds failure does not block deal
# ---------------------------------------------------------------------------

def test_picreds_failure_does_not_block_deal():
    import pathlib, tempfile
    import app.db as db_module
    from fastapi.testclient import TestClient
    from unittest.mock import patch as _patch, AsyncMock as _AM

    orig = db_module.DB_PATH
    data_hash = "e" * 64

    payload = {
        "buyer_budget": 1000.0,
        "buyer_requirements": "test dataset",
        "data_description": "test data",
        "data_hash": data_hash,
        "floor_price": 600.0,
    }

    def agent_resp(action, price):
        return {"action": action, "price": price,
                "terms": {"access_scope": "full", "duration_days": 30}, "reasoning": "test"}

    with tempfile.TemporaryDirectory() as tmp:
        db_module.DB_PATH = pathlib.Path(tmp) / "test.db"

        from app.main import app as fastapi_app
        with TestClient(fastapi_app, raise_server_exceptions=True) as client:
            with _patch("app.api.routes.search_memories", new_callable=_AM, return_value=[]), \
                 _patch("app.api.routes.add_memories", new_callable=_AM, return_value={"stored": 0, "ids": []}), \
                 _patch("app.api.routes.get_memory_hash", new_callable=_AM, return_value={"hash": "", "count": 0}), \
                 _patch("app.api.routes.audit_agent_policy", side_effect=Exception("audit unavailable")), \
                 _patch("app.api.routes.audit_deal_conduct", side_effect=Exception("audit unavailable")), \
                 _patch("app.agents.negotiation.sign_result", new_callable=_AM, return_value="deal-quote"), \
                 _patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=_AM, return_value=agent_resp("accept", 800.0)), \
                 _patch("app.agents.seller.SellerAgent.make_offer", new_callable=_AM, return_value=agent_resp("offer", 800.0)):
                response = client.post("/api/deals/run", json=payload)

        db_module.DB_PATH = orig

    assert response.status_code == 200
    body = response.json()
    assert body["agreed"] is True
    assert body["picreds"] is None
    assert body["picreds_hash"] is None
    assert body["picreds_attested"] is False
