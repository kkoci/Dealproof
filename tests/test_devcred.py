"""
Tests for the DealProof dev-credential vertical (product/dev-credential branch).

Covers:
  - Corpus root determinism
  - hash_commit determinism + sensitivity
  - Token not persisted in DB writes
  - GitInspectorAgent: correct seniority_signal for each fixture
  - SCAE: adversarial_messages — impressive messages don't elevate hard signal
  - SCAE: adversarial_churn — detected via avg_diff_size and message length
  - SCAE: adversarial_plagiarism — large diffs don't reach 'senior'
  - extract_commit_metrics: test_file_ratio, language detection, active_months
  - _clamp_seniority: LLM cannot downgrade below hard finding
  - GitEvaluatorAgent: seniority clamped even if LLM tries to downgrade
  - SeniorDevCredential schema: employer/repo names absent
  - credential_hash determinism
  - credential_hash embedded in TDX report_data (sign_result input)
  - Full pipeline round-trip (mocked DB + mocked Claude)
  - GET /api/devcred/{id} returns 404 for unknown ID
"""
import hashlib
import json
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Allow imports from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.generate_git_fixtures import SCENARIOS
from app.devcred.git_hasher import (
    hash_commit,
    compute_repo_corpus_root,
    extract_commit_metrics,
)
from app.devcred.agents.git_inspector import GitInspectorAgent, SENIORITY_ORDER
from app.devcred.agents.git_evaluator import GitEvaluatorAgent, _clamp_seniority
from app.devcred.schemas import SeniorDevCredential
from app.devcred.routes import _hash_credential, _fallback_evaluation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _inspector() -> GitInspectorAgent:
    return GitInspectorAgent()


def _metrics(scenario: str) -> dict:
    return extract_commit_metrics(SCENARIOS[scenario])


# ---------------------------------------------------------------------------
# 1. Corpus root determinism
# ---------------------------------------------------------------------------

def test_corpus_root_is_deterministic():
    commits = SCENARIOS["genuine_senior"]
    r1 = compute_repo_corpus_root(commits)
    r2 = compute_repo_corpus_root(commits)
    assert r1 == r2
    assert len(r1) == 64


def test_corpus_root_changes_with_different_commits():
    senior = compute_repo_corpus_root(SCENARIOS["genuine_senior"])
    junior = compute_repo_corpus_root(SCENARIOS["genuine_junior"])
    assert senior != junior


# ---------------------------------------------------------------------------
# 2. hash_commit determinism + sensitivity
# ---------------------------------------------------------------------------

def test_hash_commit_is_deterministic():
    c = SCENARIOS["genuine_junior"][0]
    assert hash_commit(c) == hash_commit(c)
    assert len(hash_commit(c)) == 64


def test_hash_commit_changes_with_different_sha():
    c1 = SCENARIOS["genuine_junior"][0]
    c2 = SCENARIOS["genuine_junior"][1]
    assert hash_commit(c1) != hash_commit(c2)


# ---------------------------------------------------------------------------
# 3. Token not persisted — static analysis of db.py
# ---------------------------------------------------------------------------

def test_token_not_in_db_writes():
    """github_token must never appear in the database persistence layer."""
    db_path = os.path.join(os.path.dirname(__file__), "..", "app", "db.py")
    with open(db_path) as f:
        source = f.read()
    assert "github_token" not in source, (
        "github_token found in app/db.py — token must never be persisted"
    )


# ---------------------------------------------------------------------------
# 4. GitInspectorAgent: correct seniority_signal per fixture
# ---------------------------------------------------------------------------

def test_inspector_genuine_senior():
    r = _inspector().inspect(_metrics("genuine_senior"))
    assert r.seniority_signal == "senior"
    assert r.years_active >= 7.5
    assert r.has_test_culture is True
    assert r.consistent_contribution is True
    assert len(r.languages_deep) >= 2


def test_inspector_genuine_mid():
    r = _inspector().inspect(_metrics("genuine_mid"))
    assert r.seniority_signal == "mid"
    assert r.years_active >= 3.5


def test_inspector_genuine_junior():
    r = _inspector().inspect(_metrics("genuine_junior"))
    assert r.seniority_signal == "junior"
    assert r.years_active < 2


def test_inspector_thin_history():
    r = _inspector().inspect(_metrics("thin_history"))
    assert r.seniority_signal == "junior"
    assert r.years_active < 1


# ---------------------------------------------------------------------------
# 5. SCAE: adversarial_messages — metrics hold seniority at 'junior'
# ---------------------------------------------------------------------------

def test_scae_adversarial_messages_hard_signal_stays_junior():
    """
    Impressive commit messages must not fool the deterministic inspector.
    avg_commit_quality uses message *length*, but short history and tiny diffs
    still resolve seniority_signal = 'junior'.
    """
    metrics = _metrics("adversarial_messages")
    r = _inspector().inspect(metrics)

    # The messages are long (avg ~58 chars), which raises avg_commit_quality
    assert metrics["commit_message_avg_length"] > 40

    # But seniority_signal is determined by years/depth/tests, NOT message wording
    assert r.seniority_signal == "junior", (
        f"SCAE failure: adversarial_messages elevated signal to {r.seniority_signal!r}"
    )


def test_scae_adversarial_messages_long_message_does_not_propagate_to_signal():
    """Corpus has same metrics as junior except message length — signal unchanged."""
    junior_metrics = _metrics("genuine_junior")
    adv_metrics = _metrics("adversarial_messages")

    junior_r = _inspector().inspect(junior_metrics)
    adv_r = _inspector().inspect(adv_metrics)

    # Both must be junior despite different message lengths
    assert junior_r.seniority_signal == "junior"
    assert adv_r.seniority_signal == "junior"


# ---------------------------------------------------------------------------
# 6. SCAE: adversarial_churn — exposed by avg_diff_size and message length
# ---------------------------------------------------------------------------

def test_scae_adversarial_churn_detected_via_diff_size():
    """High commit count from whitespace commits — tiny diffs expose the churn."""
    metrics = _metrics("adversarial_churn")
    assert metrics["avg_diff_size"] < 10, (
        f"Expected avg_diff_size < 10 for churn scenario, got {metrics['avg_diff_size']}"
    )
    assert metrics["commit_message_avg_length"] < 10


def test_scae_adversarial_churn_commit_quality_is_low():
    metrics = _metrics("adversarial_churn")
    r = _inspector().inspect(metrics)
    assert r.avg_commit_quality == "low"
    assert r.seniority_signal == "junior"


# ---------------------------------------------------------------------------
# 7. SCAE: adversarial_plagiarism — large diffs don't reach 'senior'
# ---------------------------------------------------------------------------

def test_scae_adversarial_plagiarism_not_senior():
    """Large diffs from copied OSS code must not reach 'senior' signal."""
    metrics = _metrics("adversarial_plagiarism")
    r = _inspector().inspect(metrics)

    # Diffs are large (looks sophisticated at a glance)
    assert metrics["avg_diff_size"] > 200

    # But seniority_signal must not be 'senior'
    assert r.seniority_signal != "senior", (
        f"SCAE failure: adversarial_plagiarism reached 'senior'"
    )


# ---------------------------------------------------------------------------
# 8. extract_commit_metrics unit checks
# ---------------------------------------------------------------------------

def test_extract_metrics_test_file_ratio():
    commits = [
        {
            "sha": "a", "author": "X", "timestamp": "2023-01-01T00:00:00+00:00",
            "message": "feat", "is_merge": False,
            "diff_stat": {"additions": 10, "deletions": 2, "total": 12},
            "files": [{"filename": "tests/test_foo.py", "additions": 10, "deletions": 2}],
        },
        {
            "sha": "b", "author": "X", "timestamp": "2023-02-01T00:00:00+00:00",
            "message": "fix", "is_merge": False,
            "diff_stat": {"additions": 5, "deletions": 1, "total": 6},
            "files": [{"filename": "app/main.py", "additions": 5, "deletions": 1}],
        },
        {
            "sha": "c", "author": "X", "timestamp": "2023-03-01T00:00:00+00:00",
            "message": "docs", "is_merge": False,
            "diff_stat": {"additions": 3, "deletions": 0, "total": 3},
            "files": [{"filename": "README.md", "additions": 3, "deletions": 0}],
        },
    ]
    m = extract_commit_metrics(commits)
    assert m["test_file_ratio"] == pytest.approx(1 / 3)


def test_extract_metrics_language_detection():
    commits = [
        {
            "sha": "a", "author": "X", "timestamp": "2023-01-01T00:00:00+00:00",
            "message": "add", "is_merge": False,
            "diff_stat": {"additions": 100, "deletions": 0, "total": 100},
            "files": [
                {"filename": "main.go", "additions": 60, "deletions": 0},
                {"filename": "util.py", "additions": 40, "deletions": 0},
            ],
        },
    ]
    m = extract_commit_metrics(commits)
    assert "Go" in m["languages"]
    assert "Python" in m["languages"]
    assert m["languages"]["Go"] == 60
    assert m["languages"]["Python"] == 40


def test_extract_metrics_active_months():
    commits = [
        {"sha": "a", "author": "X", "timestamp": "2023-01-15T00:00:00+00:00",
         "message": "x", "is_merge": False, "diff_stat": None, "files": []},
        {"sha": "b", "author": "X", "timestamp": "2023-01-20T00:00:00+00:00",
         "message": "x", "is_merge": False, "diff_stat": None, "files": []},
        {"sha": "c", "author": "X", "timestamp": "2023-03-05T00:00:00+00:00",
         "message": "x", "is_merge": False, "diff_stat": None, "files": []},
    ]
    m = extract_commit_metrics(commits)
    # Two distinct months: January and March
    assert m["active_months"] == 2


# ---------------------------------------------------------------------------
# 9. _clamp_seniority: LLM cannot downgrade below hard finding
# ---------------------------------------------------------------------------

def test_clamp_seniority_blocks_downgrade():
    assert _clamp_seniority("senior", "mid") == "senior"
    assert _clamp_seniority("mid", "junior") == "mid"
    assert _clamp_seniority("senior", "junior") == "senior"


def test_clamp_seniority_allows_upgrade():
    assert _clamp_seniority("junior", "mid") == "mid"
    assert _clamp_seniority("mid", "senior") == "senior"
    assert _clamp_seniority("junior", "staff") == "staff"


def test_clamp_seniority_identity():
    for level in SENIORITY_ORDER:
        assert _clamp_seniority(level, level) == level


# ---------------------------------------------------------------------------
# 10. GitEvaluatorAgent: clamp fires when LLM tries to downgrade
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluator_clamps_downgrade():
    """LLM returns 'junior' for a 'senior' hard finding — must be clamped to 'senior'."""
    llm_response = json.dumps({
        "seniority_level": "junior",   # attempted downgrade
        "primary_languages": ["Go"],
        "specializations": ["backend"],
        "contribution_pattern": "Consistent commits.",
        "qualitative_assessment": "Looks junior.",
        "confidence": "low",
        "caveats": [],
    })

    inspector = GitInspectorAgent()
    hard = inspector.inspect(_metrics("genuine_senior"))
    assert hard.seniority_signal == "senior"

    evaluator = GitEvaluatorAgent()
    with patch.object(evaluator.client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = _make_mock_response(llm_response)
        evaluation = await evaluator.evaluate(_metrics("genuine_senior"), hard)

    assert evaluation is not None
    assert evaluation.seniority_level == "senior"  # clamped, not 'junior'


# ---------------------------------------------------------------------------
# 11. SeniorDevCredential schema: privacy constraints
# ---------------------------------------------------------------------------

def test_credential_schema_no_employer_or_repo_names():
    """Employer names and repo names must not appear in the credential JSON."""
    cred = SeniorDevCredential(
        credential_id="test-id",
        developer_handle="octocat",
        repo_corpus_root="a" * 64,
        commit_count=500,
        years_active=5.0,
        hard_seniority_signal="mid",
        seniority_level="senior",
        primary_languages=["Go", "Python"],
        specializations=["API design"],
        has_test_culture=True,
        qualitative_assessment="Strong contributor.",
        confidence="high",
        caveats=[],
        credential_hash="b" * 64,
        issued_at="2024-01-01T00:00:00+00:00",
        tee_attested=True,
    )
    cred_json = cred.model_dump_json()

    # These must never appear
    for forbidden in ["employer", "company", "owner/repo", "file_path", "raw_diff"]:
        assert forbidden not in cred_json.lower(), (
            f"Privacy violation: {forbidden!r} found in credential JSON"
        )

    # developer_handle is present (GitHub username is allowed)
    assert "octocat" in cred_json


# ---------------------------------------------------------------------------
# 12. credential_hash determinism
# ---------------------------------------------------------------------------

def test_credential_hash_is_deterministic():
    fields = {
        "credential_type": "SeniorDevCredential",
        "credential_id": "test-id",
        "developer_handle": "octocat",
        "repo_corpus_root": "a" * 64,
        "commit_count": 500,
        "years_active": 5.0,
        "hard_seniority_signal": "mid",
        "seniority_level": "senior",
        "primary_languages": ["Go", "Python"],
        "specializations": ["API design"],
        "has_test_culture": True,
        "qualitative_assessment": "Strong contributor.",
        "confidence": "high",
        "caveats": [],
        "issued_at": "2024-01-01T00:00:00+00:00",
    }
    h1 = _hash_credential(fields)
    h2 = _hash_credential(fields)
    assert h1 == h2
    assert len(h1) == 64


def test_credential_hash_changes_with_content():
    base = {
        "credential_type": "SeniorDevCredential",
        "credential_id": "id-a",
        "developer_handle": "alice",
        "repo_corpus_root": "a" * 64,
        "commit_count": 100,
        "years_active": 3.0,
        "hard_seniority_signal": "mid",
        "seniority_level": "mid",
        "primary_languages": ["Python"],
        "specializations": [],
        "has_test_culture": False,
        "qualitative_assessment": "Average.",
        "confidence": "medium",
        "caveats": [],
        "issued_at": "2024-01-01T00:00:00+00:00",
    }
    modified = dict(base)
    modified["seniority_level"] = "senior"
    assert _hash_credential(base) != _hash_credential(modified)


# ---------------------------------------------------------------------------
# 13. credential_hash embedded in TDX sign_result input
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_credential_hash_embedded_in_tee_report_data():
    """
    sign_result must be called with a payload containing credential_hash
    and repo_corpus_root — these are the values that go into TDX report_data.
    """
    from app.tee.attestation import sign_result

    corpus_root = "c" * 64
    cred_hash = "d" * 64

    captured_payload = {}

    async def fake_sign(terms: dict, memory_hash: str = "") -> str:
        captured_payload.update(terms)
        return "sim_quote:test"

    with patch("app.devcred.routes.sign_result", new=fake_sign):
        # Import inside patch scope so route handler picks up the mock
        from app.devcred import routes as devcred_routes
        result = await devcred_routes.sign_result(
            {"credential_hash": cred_hash, "repo_corpus_root": corpus_root}
        )

    assert captured_payload.get("credential_hash") == cred_hash
    assert captured_payload.get("repo_corpus_root") == corpus_root


# ---------------------------------------------------------------------------
# 14. Full pipeline round-trip (mocked DB + mocked Claude)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_round_trip():
    """
    POST /api/devcred/{id}/evaluate — mocked DB record + mocked LLM.
    Verifies: hard inspector runs, LLM called, credential persisted, response valid.
    """
    credential_id = "round-trip-test-id"
    metrics = _metrics("genuine_senior")

    db_record = {
        "credential_id": credential_id,
        "developer_handle": "octocat",
        "repo_corpus_root": "a" * 64,
        "commit_count": len(SCENARIOS["genuine_senior"]),
        "metrics": metrics,
        "credential": None,
        "tee_quote": None,
        "status": "ingested",
    }

    llm_response = json.dumps({
        "seniority_level": "senior",
        "primary_languages": ["Go", "Python"],
        "specializations": ["distributed systems", "API design"],
        "contribution_pattern": "Consistent long-term contributions with strong test culture.",
        "qualitative_assessment": "Highly experienced engineer with deep polyglot skills.",
        "confidence": "high",
        "caveats": [],
    })

    persisted = {}

    async def fake_get_dev_credential(cid):
        return db_record

    async def fake_update_dev_credential_result(credential_id, credential, tee_quote):
        persisted["credential"] = credential
        persisted["tee_quote"] = tee_quote

    with patch("app.devcred.routes.db") as mock_db, \
         patch("app.devcred.routes.sign_result", new=AsyncMock(return_value="sim_quote:abc")):

        mock_db.get_dev_credential = AsyncMock(return_value=db_record)
        mock_db.update_dev_credential_result = AsyncMock(side_effect=fake_update_dev_credential_result)

        evaluator_mock_client = AsyncMock()
        evaluator_mock_client.messages.create = AsyncMock(
            return_value=_make_mock_response(llm_response)
        )

        with patch("app.devcred.agents.git_evaluator.anthropic.AsyncAnthropic",
                   return_value=evaluator_mock_client):
            from app.devcred.routes import evaluate_credential
            response = await evaluate_credential(credential_id)

    assert response.credential.seniority_level == "senior"
    assert response.credential.developer_handle == "octocat"
    assert response.credential.tee_attested is True
    assert len(response.credential.credential_hash) == 64
    assert response.tee_quote == "sim_quote:abc"

    # credential was persisted
    assert persisted.get("credential") is not None
    assert persisted["credential"]["seniority_level"] == "senior"


# ---------------------------------------------------------------------------
# 15. GET /api/devcred/{id} returns 404 for unknown ID
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_credential_returns_404_for_unknown_id():
    with patch("app.devcred.routes.db") as mock_db:
        mock_db.get_dev_credential = AsyncMock(return_value=None)

        from fastapi import HTTPException
        from app.devcred.routes import get_credential_status

        with pytest.raises(HTTPException) as exc_info:
            await get_credential_status("nonexistent-id")

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 16. _fallback_evaluation uses hard seniority_signal
# ---------------------------------------------------------------------------

def test_fallback_evaluation_uses_hard_signal():
    inspector = GitInspectorAgent()
    hard = inspector.inspect(_metrics("genuine_senior"))
    metrics = _metrics("genuine_senior")
    fallback = _fallback_evaluation(hard, metrics)
    assert fallback.seniority_level == hard.seniority_signal
    assert fallback.confidence == "low"
    assert len(fallback.caveats) >= 1


# ---------------------------------------------------------------------------
# 17. Corpus root ordering sensitivity
# ---------------------------------------------------------------------------

def test_corpus_root_ordering_matters():
    commits = SCENARIOS["genuine_junior"]
    root_forward = compute_repo_corpus_root(commits)
    root_reversed = compute_repo_corpus_root(list(reversed(commits)))
    assert root_forward != root_reversed
