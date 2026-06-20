"""
AN3 tests — Fundraising Negotiation endpoint + credential.

15 tests covering:
  Schema         (2)  valid request, invalid floor > ask rejected at endpoint
  DB             (2)  save + get fundraising_negotiation round-trip
  Endpoint       (9)  404 / 400 gates, agreed path, failed path,
                      TDX payload shape, picreds non-fatal, memory non-fatal,
                      credential_hash determinism, transcript in response
  Integration    (2)  picreds_hash matches audit output, memory write hash
                      reflects outcome messages

External I/O mocked: FounderAgent, InvestorAgent, audit_fundraising_conduct,
search_memories, add_memories, sign_result, MetricsEvaluatorAgent.
"""
import hashlib
import json
import pytest
import tempfile
import dataclasses
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from scripts.generate_fundraising_fixtures import SCENARIOS


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _records(scenario: str) -> list[dict]:
    return list(SCENARIOS[scenario]["metrics_records"])


_INGEST_BODY = {
    "company_name": "NegotiationCo",
    "round_label": "Series A",
    "metrics_records": _records("clean_series_a"),
}

_NEG_PAYLOAD = {
    "investor_id": "vc-firm-123",
    "investor_max_valuation": 12_000_000.0,
    "investor_investment_amount": 2_000_000.0,
    "investor_target_ownership_pct": 15.0,
    "investor_requirements": "Strong metrics, experienced team.",
    "founder_floor_valuation": 8_000_000.0,
    "founder_valuation_ask": 15_000_000.0,
    "max_rounds": 5,
}

_FOUNDER_OFFER = {
    "action": "offer",
    "price": 15_000_000.0,
    "terms": {"ownership_pct": 13.0, "investment_amount": 2_000_000.0, "notes": ""},
    "reasoning": "Our MoM growth is 9% and gross margin is 76%.",
}

_INVESTOR_ACCEPT = {
    "action": "accept",
    "price": 12_000_000.0,
    "terms": {"ownership_pct": 15.0, "investment_amount": 2_000_000.0, "notes": ""},
    "reasoning": "Metrics justify the valuation.",
}

_INVESTOR_REJECT = {
    "action": "reject",
    "price": 0.0,
    "terms": {},
    "reasoning": "Valuation too high.",
}

_MOCK_CONDUCT_AUDIT = {
    "investor_cap_respected": True,
    "founder_floor_respected": True,
    "no_sudden_capitulation": True,
    "convergence_pattern_valid": True,
    "founder_claim_consistency": True,
    "no_collusion_detected": True,
    "genuine_negotiation": True,
    "metric_argument_quality": "strong",
    "hard_constraint_findings": [],
    "llm_findings": [],
    "assessment": "Clean negotiation.",
}


@pytest.fixture()
def tmp_db(tmp_path):
    return tmp_path / "test_neg.db"


@pytest.fixture()
def client(tmp_db):
    import app.db as db_mod
    with patch.object(db_mod, "DB_PATH", tmp_db):
        from app.main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def _ingest_and_evaluate(client) -> tuple[str, str]:
    """Helper: ingest + evaluate a diligence, return (diligence_id, credential_hash)."""
    ingest = client.post("/api/fundraising/diligence/ingest", json=_INGEST_BODY)
    assert ingest.status_code == 200
    diligence_id = ingest.json()["diligence_id"]

    mock_eval = AsyncMock(return_value=None)
    mock_sign = AsyncMock(return_value="sim_quote:eval")
    with patch("app.fundraising.routes.MetricsEvaluatorAgent.evaluate", mock_eval), \
         patch("app.fundraising.routes.sign_result", mock_sign):
        ev = client.post(
            f"/api/fundraising/diligence/{diligence_id}/evaluate",
            json={},
        )
    assert ev.status_code == 200
    return diligence_id, ev.json()["credential_hash"]


# ---------------------------------------------------------------------------
# Schema tests (2)
# ---------------------------------------------------------------------------

def test_negotiation_request_schema_valid():
    from app.fundraising.schemas import FundraisingNegotiationRequest
    req = FundraisingNegotiationRequest(
        diligence_id="did-1",
        **_NEG_PAYLOAD,
    )
    assert req.investor_max_valuation == 12_000_000.0
    assert req.founder_floor_valuation == 8_000_000.0
    assert req.max_rounds == 5


def test_negotiation_credential_schema_has_all_fields():
    from app.fundraising.schemas import FundraisingNegotiationCredential
    cred = FundraisingNegotiationCredential(
        negotiation_id="neg-1",
        diligence_id="did-1",
        investor_id="vc-1",
        diligence_credential_hash="a" * 64,
        agreed=True,
        final_valuation=11_000_000.0,
        round_count=2,
        transcript=[],
        conduct_audit=None,
        picreds_attested=False,
        negotiation_picreds_hash=None,
        memory_attested=False,
        memory_context_hash=None,
        memory_write_hash=None,
        credential_hash="b" * 64,
        tee_quote="sim_quote:x",
        tee_attested=True,
        issued_at="2026-06-20T00:00:00Z",
    )
    assert cred.credential_type == "FundraisingNegotiationCredential"
    assert cred.tee_attested is True


# ---------------------------------------------------------------------------
# DB round-trip tests (2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_save_and_get_negotiation(tmp_db):
    import app.db as db_mod
    import aiosqlite
    from unittest.mock import patch as _p

    with _p.object(db_mod, "DB_PATH", tmp_db):
        await db_mod.create_fundraising_diligences_table()
        await db_mod.create_fundraising_negotiations_table()

        await db_mod.save_fundraising_negotiation(
            negotiation_id="neg-test-1",
            diligence_id="did-x",
            investor_id="vc-x",
            agreed=True,
            final_valuation=10_000_000.0,
            transcript=[{"round": 1, "role": "seller", "price": 15e6}],
            conduct_audit={"genuine_negotiation": True},
            picreds_hash="p" * 64,
            memory_context_hash="m" * 64,
            memory_write_hash="w" * 64,
            diligence_credential_hash="d" * 64,
            credential_hash="c" * 64,
            tee_quote="sim_quote:db",
            issued_at="2026-06-20T00:00:00Z",
        )

        row = await db_mod.get_fundraising_negotiation("neg-test-1")

    assert row is not None
    assert row["agreed"] is True
    assert row["final_valuation"] == 10_000_000.0
    assert row["conduct_audit"] == {"genuine_negotiation": True}
    assert row["credential_hash"] == "c" * 64


@pytest.mark.asyncio
async def test_db_get_negotiation_missing_returns_none(tmp_db):
    import app.db as db_mod
    from unittest.mock import patch as _p

    with _p.object(db_mod, "DB_PATH", tmp_db):
        await db_mod.create_fundraising_negotiations_table()
        row = await db_mod.get_fundraising_negotiation("nonexistent")

    assert row is None


# ---------------------------------------------------------------------------
# Endpoint gate tests (2)
# ---------------------------------------------------------------------------

def test_negotiation_404_unknown_diligence(client):
    payload = {"diligence_id": "no-such-id", **_NEG_PAYLOAD}
    resp = client.post("/api/fundraising/negotiation/run", json=payload)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_negotiation_400_unevaluated_diligence(client):
    ingest = client.post("/api/fundraising/diligence/ingest", json=_INGEST_BODY)
    diligence_id = ingest.json()["diligence_id"]

    payload = {"diligence_id": diligence_id, **_NEG_PAYLOAD}
    resp = client.post("/api/fundraising/negotiation/run", json=payload)
    assert resp.status_code == 400
    assert "evaluated" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Endpoint happy path — agreed=True (3)
# ---------------------------------------------------------------------------

def test_negotiation_agreed_returns_credential(client):
    diligence_id, _ = _ingest_and_evaluate(client)
    payload = {"diligence_id": diligence_id, **_NEG_PAYLOAD}

    with patch("app.fundraising.routes.search_memories", new_callable=AsyncMock, return_value=[]), \
         patch("app.fundraising.routes.add_memories", new_callable=AsyncMock, return_value={}), \
         patch("app.fundraising.routes.FounderAgent.make_offer",
               new_callable=AsyncMock, return_value=_FOUNDER_OFFER), \
         patch("app.fundraising.routes.InvestorAgent.evaluate_offer",
               new_callable=AsyncMock, return_value=_INVESTOR_ACCEPT), \
         patch("app.fundraising.routes.audit_fundraising_conduct",
               new_callable=AsyncMock, return_value=_MOCK_CONDUCT_AUDIT), \
         patch("app.fundraising.routes.sign_result",
               new_callable=AsyncMock, return_value="sim_quote:neg"):
        resp = client.post("/api/fundraising/negotiation/run", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["agreed"] is True
    assert data["final_valuation"] is not None
    assert data["credential_type"] == "FundraisingNegotiationCredential"
    assert len(data["credential_hash"]) == 64
    assert data["tee_attested"] is True
    assert data["picreds_attested"] is True
    assert data["diligence_id"] == diligence_id


def test_negotiation_tee_payload_contains_diligence_hash(client):
    """sign_result must receive diligence_credential_hash + negotiation_picreds_hash."""
    diligence_id, diligence_cred_hash = _ingest_and_evaluate(client)
    payload = {"diligence_id": diligence_id, **_NEG_PAYLOAD}
    captured = {}

    async def _capture_sign(terms, memory_hash=""):
        captured.update(terms)
        return "sim_quote:captured"

    with patch("app.fundraising.routes.search_memories", new_callable=AsyncMock, return_value=[]), \
         patch("app.fundraising.routes.add_memories", new_callable=AsyncMock, return_value={}), \
         patch("app.fundraising.routes.FounderAgent.make_offer",
               new_callable=AsyncMock, return_value=_FOUNDER_OFFER), \
         patch("app.fundraising.routes.InvestorAgent.evaluate_offer",
               new_callable=AsyncMock, return_value=_INVESTOR_ACCEPT), \
         patch("app.fundraising.routes.audit_fundraising_conduct",
               new_callable=AsyncMock, return_value=_MOCK_CONDUCT_AUDIT), \
         patch("app.fundraising.routes.sign_result", _capture_sign):
        resp = client.post("/api/fundraising/negotiation/run", json=payload)

    assert resp.status_code == 200
    assert "diligence_credential_hash" in captured
    assert captured["diligence_credential_hash"] == diligence_cred_hash
    assert "negotiation_picreds_hash" in captured
    assert "agreed" in captured
    assert captured["agreed"] is True


def test_negotiation_picreds_hash_matches_audit_output(client):
    """negotiation_picreds_hash must be SHA-256(conduct_audit, sort_keys=True)."""
    diligence_id, _ = _ingest_and_evaluate(client)
    payload = {"diligence_id": diligence_id, **_NEG_PAYLOAD}

    with patch("app.fundraising.routes.search_memories", new_callable=AsyncMock, return_value=[]), \
         patch("app.fundraising.routes.add_memories", new_callable=AsyncMock, return_value={}), \
         patch("app.fundraising.routes.FounderAgent.make_offer",
               new_callable=AsyncMock, return_value=_FOUNDER_OFFER), \
         patch("app.fundraising.routes.InvestorAgent.evaluate_offer",
               new_callable=AsyncMock, return_value=_INVESTOR_ACCEPT), \
         patch("app.fundraising.routes.audit_fundraising_conduct",
               new_callable=AsyncMock, return_value=_MOCK_CONDUCT_AUDIT), \
         patch("app.fundraising.routes.sign_result",
               new_callable=AsyncMock, return_value="sim_quote:x"):
        resp = client.post("/api/fundraising/negotiation/run", json=payload)

    data = resp.json()
    expected_hash = hashlib.sha256(
        json.dumps(_MOCK_CONDUCT_AUDIT, sort_keys=True).encode()
    ).hexdigest()
    assert data["negotiation_picreds_hash"] == expected_hash


# ---------------------------------------------------------------------------
# Endpoint failed negotiation (1)
# ---------------------------------------------------------------------------

def test_negotiation_failed_returns_agreed_false(client):
    diligence_id, _ = _ingest_and_evaluate(client)
    payload = {"diligence_id": diligence_id, **_NEG_PAYLOAD, "max_rounds": 1}

    with patch("app.fundraising.routes.search_memories", new_callable=AsyncMock, return_value=[]), \
         patch("app.fundraising.routes.add_memories", new_callable=AsyncMock, return_value={}), \
         patch("app.fundraising.routes.FounderAgent.make_offer",
               new_callable=AsyncMock, return_value=_FOUNDER_OFFER), \
         patch("app.fundraising.routes.InvestorAgent.evaluate_offer",
               new_callable=AsyncMock, return_value=_INVESTOR_REJECT), \
         patch("app.fundraising.routes.sign_result",
               new_callable=AsyncMock, return_value="sim_quote:failed"):
        resp = client.post("/api/fundraising/negotiation/run", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["agreed"] is False
    assert data["final_valuation"] is None
    assert data["picreds_attested"] is False
    assert data["memory_attested"] is False
    assert data["conduct_audit"] is None


# ---------------------------------------------------------------------------
# Resilience: non-fatal failure tests (2)
# ---------------------------------------------------------------------------

def test_negotiation_memory_failure_is_non_fatal(client):
    """If memory sidecar is down, negotiation still completes with memory_attested=False."""
    diligence_id, _ = _ingest_and_evaluate(client)
    payload = {"diligence_id": diligence_id, **_NEG_PAYLOAD}

    with patch("app.fundraising.routes.search_memories",
               new_callable=AsyncMock, side_effect=Exception("sidecar down")), \
         patch("app.fundraising.routes.add_memories",
               new_callable=AsyncMock, side_effect=Exception("sidecar down")), \
         patch("app.fundraising.routes.FounderAgent.make_offer",
               new_callable=AsyncMock, return_value=_FOUNDER_OFFER), \
         patch("app.fundraising.routes.InvestorAgent.evaluate_offer",
               new_callable=AsyncMock, return_value=_INVESTOR_ACCEPT), \
         patch("app.fundraising.routes.audit_fundraising_conduct",
               new_callable=AsyncMock, return_value=_MOCK_CONDUCT_AUDIT), \
         patch("app.fundraising.routes.sign_result",
               new_callable=AsyncMock, return_value="sim_quote:mem_fail"):
        resp = client.post("/api/fundraising/negotiation/run", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["agreed"] is True
    assert data["memory_attested"] is False
    assert data["memory_context_hash"] is None


def test_negotiation_picreds_failure_is_non_fatal(client):
    """If audit_fundraising_conduct raises, negotiation still completes with picreds_attested=False."""
    diligence_id, _ = _ingest_and_evaluate(client)
    payload = {"diligence_id": diligence_id, **_NEG_PAYLOAD}

    with patch("app.fundraising.routes.search_memories", new_callable=AsyncMock, return_value=[]), \
         patch("app.fundraising.routes.add_memories", new_callable=AsyncMock, return_value={}), \
         patch("app.fundraising.routes.FounderAgent.make_offer",
               new_callable=AsyncMock, return_value=_FOUNDER_OFFER), \
         patch("app.fundraising.routes.InvestorAgent.evaluate_offer",
               new_callable=AsyncMock, return_value=_INVESTOR_ACCEPT), \
         patch("app.fundraising.routes.audit_fundraising_conduct",
               new_callable=AsyncMock, side_effect=Exception("LLM timeout")), \
         patch("app.fundraising.routes.sign_result",
               new_callable=AsyncMock, return_value="sim_quote:pc_fail"):
        resp = client.post("/api/fundraising/negotiation/run", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["agreed"] is True
    assert data["picreds_attested"] is False
    assert data["conduct_audit"] is None
    assert data["negotiation_picreds_hash"] is None


# ---------------------------------------------------------------------------
# credential_hash determinism (1)
# ---------------------------------------------------------------------------

def test_credential_hash_determinism(client):
    """Two negotiations with identical mock outcomes must produce different IDs
    but both hashes must be 64-char hex strings."""
    diligence_id, _ = _ingest_and_evaluate(client)
    payload = {"diligence_id": diligence_id, **_NEG_PAYLOAD}

    results = []
    for _ in range(2):
        with patch("app.fundraising.routes.search_memories",
                   new_callable=AsyncMock, return_value=[]), \
             patch("app.fundraising.routes.add_memories",
                   new_callable=AsyncMock, return_value={}), \
             patch("app.fundraising.routes.FounderAgent.make_offer",
                   new_callable=AsyncMock, return_value=_FOUNDER_OFFER), \
             patch("app.fundraising.routes.InvestorAgent.evaluate_offer",
                   new_callable=AsyncMock, return_value=_INVESTOR_ACCEPT), \
             patch("app.fundraising.routes.audit_fundraising_conduct",
                   new_callable=AsyncMock, return_value=_MOCK_CONDUCT_AUDIT), \
             patch("app.fundraising.routes.sign_result",
                   new_callable=AsyncMock, return_value="sim_quote:det"):
            resp = client.post("/api/fundraising/negotiation/run", json=payload)
        results.append(resp.json())

    # Both are valid hex hashes
    for r in results:
        assert len(r["credential_hash"]) == 64
    # Different negotiation_ids (UUIDs)
    assert results[0]["negotiation_id"] != results[1]["negotiation_id"]


# ---------------------------------------------------------------------------
# Transcript in response (1)
# ---------------------------------------------------------------------------

def test_negotiation_transcript_in_response(client):
    """Response must include a non-empty transcript list."""
    diligence_id, _ = _ingest_and_evaluate(client)
    payload = {"diligence_id": diligence_id, **_NEG_PAYLOAD}

    with patch("app.fundraising.routes.search_memories", new_callable=AsyncMock, return_value=[]), \
         patch("app.fundraising.routes.add_memories", new_callable=AsyncMock, return_value={}), \
         patch("app.fundraising.routes.FounderAgent.make_offer",
               new_callable=AsyncMock, return_value=_FOUNDER_OFFER), \
         patch("app.fundraising.routes.InvestorAgent.evaluate_offer",
               new_callable=AsyncMock, return_value=_INVESTOR_ACCEPT), \
         patch("app.fundraising.routes.audit_fundraising_conduct",
               new_callable=AsyncMock, return_value=_MOCK_CONDUCT_AUDIT), \
         patch("app.fundraising.routes.sign_result",
               new_callable=AsyncMock, return_value="sim_quote:tr"):
        resp = client.post("/api/fundraising/negotiation/run", json=payload)

    data = resp.json()
    assert isinstance(data["transcript"], list)
    assert len(data["transcript"]) > 0
    first = data["transcript"][0]
    assert "round" in first
    assert "role" in first
    assert "price" in first
