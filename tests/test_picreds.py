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
    "no_collusion_detected": True,
    "genuine_negotiation": True,
    "findings": ["Buyer remained within budget. Seller held floor throughout."],
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
        {"round": 2, "role": "seller", "action": "counter", "price": 720.0},
        {"round": 2, "role": "buyer", "action": "accept", "price": 720.0},
    ]

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await audit_deal_conduct(transcript, 1000.0, 600.0, 720.0)

    # Hard constraint booleans come from deterministic checks, not LLM
    assert result["buyer_budget_respected"] is True
    assert result["seller_floor_respected"] is True
    assert result["no_sudden_capitulation"] is True
    assert result["convergence_pattern_valid"] is True
    # LLM-sourced fields
    assert result["no_collusion_detected"] is True
    assert result["genuine_negotiation"] is True
    # Hard findings are present
    assert isinstance(result["hard_constraint_findings"], list)
    assert len(result["hard_constraint_findings"]) == 4


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
# Deterministic constraint checks — pure unit tests, no mocks needed
# ---------------------------------------------------------------------------

def test_check_buyer_budget_respected_fail():
    from app.picreds.constraints import check_buyer_budget_respected
    transcript = [
        {"round": 1, "role": "seller", "action": "offer", "price": 1200.0},
        {"round": 1, "role": "buyer", "action": "counter", "price": 1100.0},
    ]
    result = check_buyer_budget_respected(transcript, buyer_budget=1000.0)
    assert result.passed is False
    assert "1100.0" in result.finding
    assert len(result.evidence) == 1


def test_check_seller_floor_respected_fail():
    from app.picreds.constraints import check_seller_floor_respected
    transcript = [
        {"round": 1, "role": "seller", "action": "offer", "price": 800.0},
        {"round": 2, "role": "seller", "action": "counter", "price": 500.0},
    ]
    result = check_seller_floor_respected(transcript, floor_price=600.0)
    assert result.passed is False
    assert "500.0" in result.finding
    assert len(result.evidence) == 1


def test_check_no_sudden_capitulation_fail():
    from app.picreds.constraints import check_no_sudden_capitulation
    # seller drops from 1000 to 400 = 60% jump, exceeds 40% threshold
    transcript = [
        {"round": 1, "role": "seller", "action": "offer", "price": 1000.0},
        {"round": 2, "role": "seller", "action": "counter", "price": 400.0},
    ]
    result = check_no_sudden_capitulation(transcript, threshold=0.40)
    assert result.passed is False
    assert "60.0%" in result.finding


def test_check_convergence_pattern_fail():
    from app.picreds.constraints import check_convergence_pattern
    # buyer goes DOWN from 700 to 600 — non-convergent
    transcript = [
        {"round": 1, "role": "seller", "action": "offer", "price": 1000.0},
        {"round": 1, "role": "buyer", "action": "counter", "price": 700.0},
        {"round": 2, "role": "seller", "action": "counter", "price": 900.0},
        {"round": 2, "role": "buyer", "action": "counter", "price": 600.0},
    ]
    result = check_convergence_pattern(transcript)
    assert result.passed is False
    assert len(result.evidence) == 1


def test_run_all_checks_clean_transcript():
    from app.picreds.constraints import run_all_checks
    transcript = [
        {"round": 1, "role": "seller", "action": "offer", "price": 900.0},
        {"round": 1, "role": "buyer", "action": "counter", "price": 650.0},
        {"round": 2, "role": "seller", "action": "counter", "price": 780.0},
        {"round": 2, "role": "buyer", "action": "counter", "price": 720.0},
        {"round": 3, "role": "seller", "action": "accept", "price": 720.0},
    ]
    results = run_all_checks(transcript, buyer_budget=1000.0, floor_price=600.0)
    assert all(r.passed for r in results.values())
    assert set(results.keys()) == {"buyer_budget", "seller_floor", "capitulation", "convergence"}


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
