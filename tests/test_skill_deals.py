"""
Skill deal tests — Phase SN3.

Covers:
  - SkillDealRequest schema validation (price range constraints)
  - SkillExecutionReceipt schema
  - SkillExecutionAgent.execute(): happy path, error propagation, hash determinism
  - POST /api/deals/skill: agreed deal, failed negotiation, skill execution error
  - TDX attestation: report_data contains picreds_hash + skill_receipt_hash (SN3)

All Claude API and tappd calls are mocked.  Skill execution is mocked via
run_skill so no real ffmpeg / PIL / network calls are made.
DB uses a real tmp-file aiosqlite so persistence is tested end-to-end.
"""

import hashlib
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

def test_skill_deal_request_valid():
    from app.api.schemas import SkillDealRequest
    req = SkillDealRequest(
        skill_id="test.skill.v1",
        skill_path="/tee/skill.json",
        tee_root="/tee",
        buyer_input_path="/tmp/photo.jpg",
        asking_price=25.0,
        minimum_acceptable_price=15.0,
        buyer_budget=30.0,
        usage_terms="single_use",
    )
    assert req.asking_price == 25.0
    assert req.minimum_acceptable_price == 15.0
    assert req.buyer_budget == 30.0


def test_skill_deal_request_floor_above_asking_raises():
    from app.api.schemas import SkillDealRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="minimum_acceptable_price"):
        SkillDealRequest(
            skill_id="s",
            skill_path="/s.json",
            tee_root="/",
            buyer_input_path="/i.jpg",
            asking_price=10.0,
            minimum_acceptable_price=20.0,  # above asking — invalid
            buyer_budget=30.0,
        )


def test_skill_deal_request_budget_below_floor_raises():
    from app.api.schemas import SkillDealRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="buyer_budget"):
        SkillDealRequest(
            skill_id="s",
            skill_path="/s.json",
            tee_root="/",
            buyer_input_path="/i.jpg",
            asking_price=25.0,
            minimum_acceptable_price=20.0,
            buyer_budget=10.0,  # below floor — invalid
        )


def test_skill_execution_receipt_schema():
    from app.api.schemas import SkillExecutionReceipt
    receipt = SkillExecutionReceipt(
        skill_id="test.skill",
        input_sha256="a" * 64,
        output_sha256="b" * 64,
        lora_sha256="FILL_AT_PACKAGING_TIME",
        backend="pil-style:local",
        pipeline_steps=["normalize", "style_inference", "grade"],
        receipt_hash="c" * 64,
    )
    assert receipt.receipt_hash == "c" * 64
    assert receipt.backend == "pil-style:local"


# ---------------------------------------------------------------------------
# SkillExecutionAgent unit tests
# ---------------------------------------------------------------------------

def _fake_run_skill_result(skill_path, input_path, output_path, mock=False, tee_root=""):
    """Minimal run_skill() return value for mocking."""
    return {
        "skill_id": "test-skill",
        "input_sha256": hashlib.sha256(b"input").hexdigest(),
        "output_sha256": hashlib.sha256(b"output").hexdigest(),
        "lora_sha256": "FILL_AT_PACKAGING_TIME",
        "pipeline_steps": ["normalize", "style_inference", "grade"],
        "chutes_aci_quote": None,
    }


def test_skill_execution_agent_happy_path(tmp_path):
    """execute() returns a SkillExecutionReceipt with a non-empty receipt_hash."""
    from app.agents.skill_execution import SkillExecutionAgent
    from app.api.schemas import SkillExecutionReceipt

    with patch("app.agents.skill_execution.run_skill", side_effect=_fake_run_skill_result):
        agent = SkillExecutionAgent()
        receipt = agent.execute(
            skill_path="skill.json",
            input_path=str(tmp_path / "in.jpg"),
            output_path=str(tmp_path / "out.jpg"),
            tee_root=str(tmp_path),
        )

    assert isinstance(receipt, SkillExecutionReceipt)
    assert receipt.skill_id == "test-skill"
    assert len(receipt.receipt_hash) == 64
    assert receipt.backend == ""  # chutes_aci_quote was None


def test_skill_execution_agent_raises_on_failure(tmp_path):
    """execute() wraps pipeline errors in SkillExecutionError — never swallows."""
    from app.agents.skill_execution import SkillExecutionAgent, SkillExecutionError

    with patch("app.agents.skill_execution.run_skill", side_effect=RuntimeError("ffmpeg died")):
        agent = SkillExecutionAgent()
        with pytest.raises(SkillExecutionError, match="ffmpeg died"):
            agent.execute("skill.json", str(tmp_path / "in.jpg"), str(tmp_path / "out.jpg"), "")


def test_skill_execution_receipt_hash_deterministic(tmp_path):
    """Same inputs always produce the same receipt_hash."""
    from app.agents.skill_execution import SkillExecutionAgent

    with patch("app.agents.skill_execution.run_skill", side_effect=_fake_run_skill_result):
        agent = SkillExecutionAgent()
        r1 = agent.execute("skill.json", "in.jpg", "out.jpg", "")
        r2 = agent.execute("skill.json", "in.jpg", "out.jpg", "")

    assert r1.receipt_hash == r2.receipt_hash


# ---------------------------------------------------------------------------
# HTTP endpoint tests — POST /api/deals/skill
# ---------------------------------------------------------------------------

def _agent_json(action: str, price: float, terms: dict | None = None):
    m = MagicMock()
    m.content = [MagicMock(text=json.dumps({
        "action": action,
        "price": price,
        "terms": terms or {},
        "reasoning": "test",
    }))]
    return m


def _skill_payload(tmp_path: Path) -> dict:
    """Minimal valid SkillDealRequest payload pointing at tmp files."""
    skill_json = tmp_path / "skill.json"
    skill_json.write_text(json.dumps({
        "schemaVersion": "skill.tee.v1",
        "id": "test-skill",
        "label": "Test Skill",
        "description": "A test style transfer skill.",
        "pipeline": [],
    }))
    input_jpg = tmp_path / "input.jpg"
    input_jpg.write_bytes(b"fake-jpeg")
    return {
        "skill_id": "test.skill.v1",
        "skill_path": str(skill_json),
        "tee_root": str(tmp_path),
        "buyer_input_path": str(input_jpg),
        "asking_price": 25.0,
        "minimum_acceptable_price": 15.0,
        "buyer_budget": 30.0,
        "usage_terms": "single_use",
    }


@pytest.fixture()
def test_client(tmp_path):
    """FastAPI TestClient with tmp-file DB and mocked tappd."""
    from fastapi.testclient import TestClient
    from app.main import app
    import app.api.routes as routes_mod

    db_path = str(tmp_path / "test.db")
    with patch.object(routes_mod.db, "db_path", db_path), \
         patch.object(routes_mod.db, "_conn", None):
        with TestClient(app) as client:
            yield client


def _agreed_response():
    return {"action": "accept", "price": 22.0, "terms": {"access_scope": "single_use"}, "reasoning": "ok"}


def _rejected_response():
    return {"action": "reject", "price": 0.0, "terms": {}, "reasoning": "no"}


def _offer_response(price: float = 22.0):
    return {"action": "offer", "price": price, "terms": {}, "reasoning": "opening"}


def test_post_skill_deal_agreed(tmp_path):
    """Agreed skill deal returns receipt, picreds, audit_report, and attestation."""
    import app.db as db_module
    from fastapi.testclient import TestClient
    from app.main import app

    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "test.db"

    payload = _skill_payload(tmp_path)

    mock_audit = MagicMock()
    mock_audit.genuine_negotiation = True
    mock_audit.round_count = 1
    mock_audit.final_price = 22.0
    mock_audit.summary = "Clean deal."
    mock_audit.credential_hash = "a" * 64

    try:
        with patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock, return_value=_agreed_response()), \
             patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock, return_value=_offer_response()), \
             patch("app.agents.skill_execution.run_skill", side_effect=_fake_run_skill_result), \
             patch("app.api.routes.audit_agent_policy", new_callable=AsyncMock, return_value={"compliant": True}), \
             patch("app.api.routes.audit_deal_conduct", new_callable=AsyncMock, return_value={"genuine_negotiation": True}), \
             patch("app.api.routes.AuditorAgent") as mock_auditor_cls:

            mock_auditor_cls.return_value.audit = AsyncMock(return_value=mock_audit)

            with TestClient(app) as client:
                response = client.post("/api/deals/skill", json=payload)
    finally:
        db_module.DB_PATH = original_db_path

    assert response.status_code == 200
    data = response.json()
    assert data["agreed"] is True
    assert data["final_price"] == 22.0
    assert data["skill_execution_receipt"] is not None
    assert data["skill_execution_receipt"]["receipt_hash"] != ""
    assert data["picreds_hash"] is not None
    assert data["picreds_attested"] is True
    assert data["attestation"] is not None
    assert data["audit_error"] is None or data["audit_error"] == ""


def test_post_skill_deal_negotiation_fails(tmp_path):
    """Failed negotiation: agreed=False, skill_execution_receipt absent."""
    import app.db as db_module
    from fastapi.testclient import TestClient
    from app.main import app

    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "test.db"

    payload = _skill_payload(tmp_path)

    try:
        with patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock, return_value=_rejected_response()), \
             patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock, return_value=_offer_response(9999.0)), \
             patch("app.agents.skill_execution.run_skill", side_effect=_fake_run_skill_result):

            with TestClient(app) as client:
                response = client.post("/api/deals/skill", json=payload)
    finally:
        db_module.DB_PATH = original_db_path

    assert response.status_code == 200
    data = response.json()
    assert data["agreed"] is False
    assert data["skill_execution_receipt"] is None
    assert data["attestation"] is None


def test_post_skill_deal_execution_error_is_non_fatal(tmp_path):
    """Skill execution error surfaces in audit_error but agreed=True and deal persists."""
    import app.db as db_module
    from fastapi.testclient import TestClient
    from app.main import app

    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "test.db"

    payload = _skill_payload(tmp_path)

    try:
        with patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock, return_value=_agreed_response()), \
             patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock, return_value=_offer_response()), \
             patch("app.agents.skill_execution.run_skill", side_effect=RuntimeError("ffmpeg exploded")), \
             patch("app.api.routes.audit_agent_policy", new_callable=AsyncMock, return_value={"compliant": True}), \
             patch("app.api.routes.audit_deal_conduct", new_callable=AsyncMock, return_value={"genuine_negotiation": True}), \
             patch("app.api.routes.AuditorAgent") as mock_auditor_cls:

            mock_auditor_cls.return_value.audit = AsyncMock(return_value=None)

            with TestClient(app) as client:
                response = client.post("/api/deals/skill", json=payload)
    finally:
        db_module.DB_PATH = original_db_path

    assert response.status_code == 200
    data = response.json()
    assert data["agreed"] is True
    assert data["skill_execution_receipt"] is None
    assert "SkillExecutionError" in (data["audit_error"] or "")


# ---------------------------------------------------------------------------
# SN3: attestation report_data contains picreds_hash + skill_receipt_hash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skill_attestation_report_data_contains_receipt_hash():
    """
    SN3: the TDX attestation for a skill deal binds both picreds_hash and
    skill_receipt_hash in report_data — verifiable from the quote alone.

    We mock sign_result at the production level, capture report_data, and
    confirm it is SHA-256 of the canonical payload containing both hashes.
    """
    import app.tee.attestation as attestation_mod

    fake_picreds_hash = "p" * 64
    fake_receipt_hash = "r" * 64

    attested_payload = {
        "final_price": 20.0,
        "terms": {"access_scope": "single_use"},
        "skill_id": "test-skill",
        "picreds_hash": fake_picreds_hash,
        "picreds_attested": True,
        "skill_receipt_hash": fake_receipt_hash,
        "skill_attested": True,
    }

    fake_quote = "cc" * 128
    mock_response = MagicMock()
    mock_response.json.return_value = {"quote": fake_quote, "event_log": ""}
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(attestation_mod.settings, "tee_mode", "production"), \
         patch("httpx.AsyncHTTPTransport"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        await attestation_mod.sign_result(attested_payload)

    call_args = mock_client.post.call_args
    report_data_hex = call_args[1]["json"]["report_data"]

    assert len(report_data_hex) == 128, "report_data must be 64 bytes (128 hex chars)"
    assert report_data_hex[64:] == "00" * 32, "last 32 bytes must be zero-padded"

    expected_digest = hashlib.sha256(
        json.dumps(attested_payload, sort_keys=True).encode()
    ).hexdigest()
    assert report_data_hex[:64] == expected_digest, (
        "First 32 bytes of report_data must be SHA-256 of the canonical payload "
        "including both picreds_hash and skill_receipt_hash"
    )
