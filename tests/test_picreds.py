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


# ---------------------------------------------------------------------------
# AN2 — Fundraising πCreds: _extract_claims_from_reasoning
# ---------------------------------------------------------------------------

_INSPECTION = {
    "mom_growth_computed":   0.092,
    "gross_margin_computed": 0.762,
    "runway_months_computed": 14.1,
    "churn_rate_computed":   0.025,
}


def test_extract_claims_num_first():
    from app.picreds.constraints import _extract_claims_from_reasoning
    claims = _extract_claims_from_reasoning("25% MoM growth and 76% gross margin")
    assert claims.get("mom_growth") == [0.25]
    assert claims.get("gross_margin") == [0.76]


def test_extract_claims_kwd_first():
    from app.picreds.constraints import _extract_claims_from_reasoning
    claims = _extract_claims_from_reasoning("MoM growth is 9.2% and gross margin of 76%")
    assert claims["mom_growth"] == [0.092]
    assert claims["gross_margin"] == [0.76]


def test_extract_claims_runway_and_churn():
    from app.picreds.constraints import _extract_claims_from_reasoning
    claims = _extract_claims_from_reasoning("runway of 14 months, monthly churn of 2.5%")
    assert claims["runway_months"] == [14.0]
    assert claims["churn_rate"] == [0.025]


def test_extract_claims_dedup_same_value():
    """Same value matched by both orderings should appear once."""
    from app.picreds.constraints import _extract_claims_from_reasoning
    claims = _extract_claims_from_reasoning("9.2% MoM growth; MoM growth is 9.2%")
    assert claims["mom_growth"] == [0.092]


def test_extract_claims_no_metrics():
    from app.picreds.constraints import _extract_claims_from_reasoning
    claims = _extract_claims_from_reasoning("Our team is world-class and our market is huge.")
    assert claims == {}


# ---------------------------------------------------------------------------
# AN2 — check_founder_claim_consistency
# ---------------------------------------------------------------------------

def test_founder_claim_consistency_honest_pass():
    from app.picreds.constraints import check_founder_claim_consistency
    result = check_founder_claim_consistency(
        [{"role": "seller", "round": 1, "price": 15e6,
          "reasoning": "Our MoM growth is 9.2% and gross margin is 76%."}],
        _INSPECTION,
    )
    assert result.passed is True


def test_founder_claim_consistency_scae_inflated_growth():
    """Founder claims 25% MoM growth; hard finding is 9.2% — >15% relative error."""
    from app.picreds.constraints import check_founder_claim_consistency
    result = check_founder_claim_consistency(
        [{"role": "seller", "round": 1, "price": 20e6,
          "reasoning": "Our MoM growth is 25%, justifying a premium valuation."}],
        _INSPECTION,
    )
    assert result.passed is False
    assert "mom" in result.finding.lower() or "growth" in result.finding.lower()
    assert len(result.evidence) == 1


def test_founder_claim_consistency_inflated_runway():
    from app.picreds.constraints import check_founder_claim_consistency
    result = check_founder_claim_consistency(
        [{"role": "seller", "round": 1, "price": 15e6,
          "reasoning": "We have runway of 30 months, so no pressure."}],
        _INSPECTION,
    )
    assert result.passed is False


def test_founder_claim_consistency_buyer_role_ignored():
    """InvestorAgent (buyer role) claims are not checked."""
    from app.picreds.constraints import check_founder_claim_consistency
    result = check_founder_claim_consistency(
        [{"role": "buyer", "round": 1, "price": 10e6,
          "reasoning": "MoM growth is 25%"}],
        _INSPECTION,
    )
    assert result.passed is True


def test_founder_claim_consistency_missing_inspection_key_skipped():
    """If a metric key is absent from inspection_report, that metric is skipped."""
    from app.picreds.constraints import check_founder_claim_consistency
    result = check_founder_claim_consistency(
        [{"role": "seller", "round": 1, "price": 15e6,
          "reasoning": "MoM growth is 25%"}],
        {},  # empty inspection — no hard findings → nothing to check
    )
    assert result.passed is True


# ---------------------------------------------------------------------------
# AN2 — check_investor_cap_respected
# ---------------------------------------------------------------------------

def test_investor_cap_respected_pass():
    from app.picreds.constraints import check_investor_cap_respected
    result = check_investor_cap_respected(
        [{"round": 1, "role": "buyer", "price": 10e6}], 12e6
    )
    assert result.passed is True
    assert result.check_name == "investor_cap_respected"


def test_investor_cap_respected_fail():
    from app.picreds.constraints import check_investor_cap_respected
    result = check_investor_cap_respected(
        [{"round": 1, "role": "buyer", "price": 13_500_000}], 12_000_000
    )
    assert result.passed is False
    assert "valuation cap" in result.finding


# ---------------------------------------------------------------------------
# AN2 — run_fundraising_checks
# ---------------------------------------------------------------------------

def test_run_fundraising_checks_all_pass():
    from app.picreds.constraints import run_fundraising_checks
    transcript = [
        {"role": "seller", "round": 1, "price": 15e6,
         "reasoning": "MoM growth is 9% and gross margin is 76%."},
        {"role": "buyer",  "round": 1, "price": 10e6, "reasoning": ""},
        {"role": "seller", "round": 2, "price": 12e6, "reasoning": ""},
        {"role": "buyer",  "round": 2, "price": 11.5e6, "reasoning": ""},
    ]
    results = run_fundraising_checks(
        transcript, investor_cap=12e6, floor_valuation=8e6,
        inspection_report=_INSPECTION,
    )
    expected_keys = {"investor_cap", "founder_floor", "capitulation", "convergence",
                     "founder_claim_consistency"}
    assert set(results.keys()) == expected_keys
    assert all(r.passed for r in results.values()), \
        [(k, r.finding) for k, r in results.items() if not r.passed]


def test_run_fundraising_checks_scae_flagged():
    from app.picreds.constraints import run_fundraising_checks
    transcript = [
        {"role": "seller", "round": 1, "price": 15e6,
         "reasoning": "We have 30% MoM growth — a clear Series A signal."},
    ]
    results = run_fundraising_checks(
        transcript, investor_cap=20e6, floor_valuation=8e6,
        inspection_report=_INSPECTION,
    )
    assert results["founder_claim_consistency"].passed is False
    # Other checks pass
    assert results["investor_cap"].passed is True
    assert results["founder_floor"].passed is True


# ---------------------------------------------------------------------------
# AN2 — audit_fundraising_conduct (mocked LLM)
# ---------------------------------------------------------------------------

FUNDRAISING_CONDUCT_RESPONSE = {
    "no_collusion_detected": True,
    "genuine_negotiation": True,
    "metric_argument_quality": "strong",
    "findings": ["Founder arguments grounded in attested metrics."],
    "assessment": "Both agents complied with their hard constraints.",
}


@pytest.mark.asyncio
async def test_audit_fundraising_conduct_all_pass():
    from app.picreds.auditor import audit_fundraising_conduct

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(FUNDRAISING_CONDUCT_RESPONSE)
    )

    transcript = [
        {"role": "seller", "round": 1, "price": 15e6,
         "reasoning": "MoM growth is 9% and margin is 76%."},
        {"role": "buyer",  "round": 1, "price": 10e6, "reasoning": ""},
        {"role": "seller", "round": 2, "price": 12e6, "reasoning": ""},
        {"role": "buyer",  "round": 2, "price": 11.5e6, "reasoning": ""},
    ]

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await audit_fundraising_conduct(
            transcript,
            investor_cap=12e6,
            floor_valuation=8e6,
            final_valuation=11.5e6,
            inspection_report=_INSPECTION,
        )

    assert result["investor_cap_respected"] is True
    assert result["founder_floor_respected"] is True
    assert result["no_sudden_capitulation"] is True
    assert result["convergence_pattern_valid"] is True
    assert result["founder_claim_consistency"] is True
    assert result["genuine_negotiation"] is True
    assert result["no_collusion_detected"] is True
    assert result["metric_argument_quality"] == "strong"
    assert len(result["hard_constraint_findings"]) == 5


@pytest.mark.asyncio
async def test_audit_fundraising_conduct_scae_overrides_llm():
    """If founder_claim_consistency fails, genuine_negotiation is forced False."""
    from app.picreds.auditor import audit_fundraising_conduct

    # LLM claims genuine — but hard check will fail due to inflated claims
    llm_says_genuine = {**FUNDRAISING_CONDUCT_RESPONSE, "genuine_negotiation": True}
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(llm_says_genuine)
    )

    transcript = [
        {"role": "seller", "round": 1, "price": 15e6,
         "reasoning": "We have 50% MoM growth — industry-leading metrics."},
    ]

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await audit_fundraising_conduct(
            transcript,
            investor_cap=20e6,
            floor_valuation=8e6,
            final_valuation=15e6,
            inspection_report=_INSPECTION,
        )

    assert result["founder_claim_consistency"] is False
    # Code override: LLM said True but hard check failed → must be False
    assert result["genuine_negotiation"] is False
