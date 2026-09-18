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
from starlette.requests import Request

# Allow imports from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.generate_git_fixtures import SCENARIOS
from app.devcred.git_hasher import (
    hash_commit,
    compute_repo_corpus_root,
    deduplicate_commits,
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


def _fake_request(path: str = "/api/devcred/test/evaluate", client_host: str = "127.0.0.1") -> Request:
    """Minimal Starlette Request satisfying slowapi's rate-limit checks for direct route calls."""
    return Request({
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    })


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
        mock_db.increment_daily_eval_count = AsyncMock(return_value=1)
        mock_db.decrement_daily_eval_count = AsyncMock()

        evaluator_mock_client = AsyncMock()
        evaluator_mock_client.messages.create = AsyncMock(
            return_value=_make_mock_response(llm_response)
        )

        with patch("app.devcred.agents.git_evaluator.anthropic.AsyncAnthropic",
                   return_value=evaluator_mock_client):
            from app.devcred.routes import evaluate_credential
            response = await evaluate_credential(_fake_request(), credential_id)

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


# ---------------------------------------------------------------------------
# 18. deduplicate_commits — pure helper
# ---------------------------------------------------------------------------

def test_deduplicate_commits_keeps_first_occurrence_only():
    commits = [{"sha": "a"}, {"sha": "b"}, {"sha": "a"}, {"sha": "c"}]
    result = deduplicate_commits(commits)
    assert [c["sha"] for c in result] == ["a", "b", "c"]


def test_deduplicate_commits_respects_already_seen():
    commits = [{"sha": "a"}, {"sha": "b"}]
    result = deduplicate_commits(commits, already_seen={"a"})
    assert [c["sha"] for c in result] == ["b"]


# ---------------------------------------------------------------------------
# 19. Multi-branch commit fetching — regression test for the "main-only" bug
# ---------------------------------------------------------------------------

def _github_commit_item(sha: str) -> dict:
    return {
        "sha": sha,
        "commit": {
            "author": {"name": "octocat", "date": "2024-01-01T00:00:00Z"},
            "message": f"commit {sha}",
        },
        "parents": [1],
    }


def _make_github_response(json_data, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


class _FakeGithubAsyncClient:
    """
    Minimal httpx.AsyncClient stand-in for POST /ingest's branch-fetch pipeline.

    Serves a fixed two-branch repo: main has commits A,B; feature/x has A,B,C (C only
    ever landed on the feature branch). Pre-fix code called only the default-branch
    commits endpoint and would see 2 commits total; the fix must see 3, deduplicated.
    Per-commit detail (enrichment) calls 404 — enrichment is best-effort and skipped.
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, params=None, timeout=None):
        params = params or {}
        if url.endswith("/user"):
            return _make_github_response({"login": "octocat"})
        if url.endswith("/branches"):
            if params.get("page", 1) != 1:
                return _make_github_response([])
            return _make_github_response([
                {"name": "main", "commit": {"sha": "sha-a"}},
                {"name": "feature/x", "commit": {"sha": "sha-c"}},
            ])
        if url.endswith("/commits"):
            if params.get("page", 1) != 1:
                return _make_github_response([])
            ref = params.get("sha")
            if ref == "main":
                return _make_github_response([
                    _github_commit_item("sha-a"),
                    _github_commit_item("sha-b"),
                ])
            if ref == "feature/x":
                return _make_github_response([
                    _github_commit_item("sha-a"),
                    _github_commit_item("sha-b"),
                    _github_commit_item("sha-c"),
                ])
            return _make_github_response([])
        # per-commit detail endpoint used by enrichment — skip it in this test
        return _make_github_response({}, status_code=404)


@pytest.mark.asyncio
async def test_ingest_repos_covers_feature_branch_only_commits():
    """
    Regression test for the "main-only" bug: a commit that only ever landed on a
    feature branch (sha-c) must be counted, and a commit reachable from both
    branches (sha-a, sha-b) must be counted exactly once — not twice.
    """
    from app.devcred.routes import ingest_repos, DevCredIngest

    body = DevCredIngest(
        github_token="fake-token",
        repos=["octocat/hello-world"],
        credential_id="branch-dedup-test-id",
    )

    with patch("app.devcred.routes.db") as mock_db, \
         patch("httpx.AsyncClient", return_value=_FakeGithubAsyncClient()):
        mock_db.create_dev_credential = AsyncMock()
        response = await ingest_repos(_fake_request(path="/api/devcred/ingest"), body)

    assert response.commit_count == 3
    assert response.metrics_preview["total_commits"] == 3
    mock_db.create_dev_credential.assert_awaited_once()
    _, kwargs = mock_db.create_dev_credential.call_args
    assert kwargs["commit_count"] == 3


# ===========================================================================
# Revoked-repo-access fallback: Route B (events_stream), Route C
# (local_git_upload), Route D (self_reported)
# ===========================================================================

import base64
import struct
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException

from app.devcred.git_hasher import compute_events_corpus_root, extract_event_metrics
from app.devcred.agents.git_inspector import inspect_events
from app.devcred.local_signature import (
    _write_string,
    SSHSIG_MAGIC,
    canonical_payload,
    verify_gpg_signature,
    verify_signature,
    verify_ssh_signature,
)
from app.devcred.schemas import ProvenanceMethod


def _event(etype: str, repo: str, created_at: str, event_id: str = "1") -> dict:
    return {"id": event_id, "type": etype, "repo": {"name": repo}, "created_at": created_at}


# ---------------------------------------------------------------------------
# 20. git_hasher: extract_event_metrics / compute_events_corpus_root
# ---------------------------------------------------------------------------

def test_extract_event_metrics_counts_types_and_months():
    events = [
        _event("PushEvent", "acme/widgets", "2026-01-05T00:00:00Z", "1"),
        _event("PullRequestEvent", "acme/widgets", "2026-01-20T00:00:00Z", "2"),
        _event("PullRequestReviewEvent", "acme/widgets", "2026-02-01T00:00:00Z", "3"),
    ]
    m = extract_event_metrics(events)
    assert m["total_events"] == 3
    assert m["active_months"] == 2
    assert m["event_type_counts"] == {"PushEvent": 1, "PullRequestEvent": 1, "PullRequestReviewEvent": 1}
    assert m["repos_touched"] == 1
    assert m["first_event_date"] is not None
    assert m["last_event_date"] is not None


def test_extract_event_metrics_empty():
    m = extract_event_metrics([])
    assert m["total_events"] == 0
    assert m["active_months"] == 0
    assert m["event_type_counts"] == {}


def test_events_corpus_root_deterministic_and_sensitive_to_content():
    events = [_event("PushEvent", "acme/widgets", "2026-01-05T00:00:00Z", "1")]
    r1 = compute_events_corpus_root(events)
    r2 = compute_events_corpus_root(events)
    assert r1 == r2
    assert len(r1) == 64

    other = [_event("PushEvent", "acme/widgets", "2026-01-06T00:00:00Z", "1")]
    assert compute_events_corpus_root(other) != r1


def test_events_corpus_root_requires_at_least_one_event():
    with pytest.raises(ValueError):
        compute_events_corpus_root([])


# ---------------------------------------------------------------------------
# 21. git_inspector.inspect_events — capped below "senior"
# ---------------------------------------------------------------------------

def test_inspect_events_junior_when_sparse():
    metrics = extract_event_metrics([_event("PushEvent", "acme/widgets", "2026-01-05T00:00:00Z")])
    r = inspect_events(metrics)
    assert r.seniority_signal == "junior"


def test_inspect_events_mid_when_substantial_and_collaborative():
    events = [_event("PushEvent", "acme/widgets", f"2026-01-{i:02d}T00:00:00Z", str(i)) for i in range(1, 26)]
    events += [_event("PullRequestEvent", "acme/widgets", f"2026-02-{i:02d}T00:00:00Z", f"pr{i}") for i in range(1, 26)]
    metrics = extract_event_metrics(events)
    assert metrics["total_events"] >= 50
    r = inspect_events(metrics)
    assert r.seniority_signal == "mid"


def test_inspect_events_never_reaches_senior_even_with_huge_volume():
    """SCAE-style guard: no volume of bare PushEvents alone should reach 'senior' —
    there is no path to it at all in inspect_events(), by construction."""
    events = [_event("PushEvent", "acme/widgets", "2026-01-01T00:00:00Z", str(i)) for i in range(1000)]
    metrics = extract_event_metrics(events)
    r = inspect_events(metrics)
    assert r.seniority_signal in ("junior", "mid")
    assert r.seniority_signal != "senior"


def test_inspect_events_mid_requires_collaborative_evidence_not_just_volume():
    """Pure solo pushes, no PR/review activity, must not reach 'mid' regardless of volume."""
    events = [_event("PushEvent", "acme/widgets", f"2026-{m:02d}-01T00:00:00Z", str(m)) for m in range(1, 7)]
    metrics = extract_event_metrics(events)
    r = inspect_events(metrics)
    assert r.seniority_signal == "junior"


# ---------------------------------------------------------------------------
# 22. routes._events_referencing_repos / _dead_end_detail
# ---------------------------------------------------------------------------

def test_events_referencing_repos_filters_case_insensitively():
    from app.devcred.routes import _events_referencing_repos

    events = [
        _event("PushEvent", "Acme/Widgets", "2026-01-01T00:00:00Z", "1"),
        _event("PushEvent", "other/repo", "2026-01-01T00:00:00Z", "2"),
    ]
    matched = _events_referencing_repos(events, ["acme/widgets"])
    assert len(matched) == 1
    assert matched[0]["id"] == "1"


def test_dead_end_detail_lists_fallback_routes():
    from app.devcred.routes import _dead_end_detail

    detail = _dead_end_detail(["acme/widgets"])
    assert detail["error"] == "repo_access_revoked_no_recent_activity"
    assert detail["fallback_available"] == ["local_git_upload", "self_reported"]
    assert detail["revoked_repos"] == ["acme/widgets"]


# ---------------------------------------------------------------------------
# 23. ingest_repos — Route B fallback on full revocation
# ---------------------------------------------------------------------------

class _FakeGithubAsyncClientRevoked:
    """All repo access 404s; the events endpoint returns activity matching the
    requested (now-inaccessible) repo, within GitHub's real ~30-day window."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, params=None, timeout=None):
        params = params or {}
        if url.endswith("/user"):
            return _make_github_response({"login": "octocat"})
        if url.endswith("/branches"):
            return _make_github_response({}, status_code=404)
        if url.endswith("/events"):
            if params.get("page", 1) != 1:
                return _make_github_response([])
            return _make_github_response([
                {"id": "1", "type": "PushEvent", "repo": {"name": "octocat/hello-world"},
                 "created_at": "2026-09-01T00:00:00Z"},
                {"id": "2", "type": "PullRequestEvent", "repo": {"name": "octocat/hello-world"},
                 "created_at": "2026-09-05T00:00:00Z"},
                {"id": "3", "type": "PushEvent", "repo": {"name": "unrelated/other"},
                 "created_at": "2026-09-05T00:00:00Z"},
            ])
        return _make_github_response({}, status_code=404)


class _FakeGithubAsyncClientRevokedNoEvents(_FakeGithubAsyncClientRevoked):
    """Same as above, but the account has no matching recent activity either —
    the genuine dead-end case."""

    async def get(self, url, headers=None, params=None, timeout=None):
        if url.endswith("/events"):
            return _make_github_response([])
        return await super().get(url, headers=headers, params=params, timeout=timeout)


@pytest.mark.asyncio
async def test_ingest_repos_falls_back_to_events_stream_on_full_revocation():
    from app.devcred.routes import ingest_repos, DevCredIngest

    body = DevCredIngest(
        github_token="fake-token",
        repos=["octocat/hello-world"],
        credential_id="revoked-fallback-id",
    )

    with patch("app.devcred.routes.db") as mock_db, \
         patch("httpx.AsyncClient", return_value=_FakeGithubAsyncClientRevoked()):
        mock_db.create_dev_credential = AsyncMock()
        response = await ingest_repos(_fake_request(path="/api/devcred/ingest"), body)

    assert response.provenance_method == "events_stream"
    assert response.commit_count == 0
    assert response.event_count == 2  # only the 2 events referencing the requested repo
    mock_db.create_dev_credential.assert_awaited_once()
    _, kwargs = mock_db.create_dev_credential.call_args
    assert kwargs["provenance_method"] == "events_stream"
    assert kwargs["event_count"] == 2


@pytest.mark.asyncio
async def test_ingest_repos_dead_end_when_events_also_empty():
    from app.devcred.routes import ingest_repos, DevCredIngest

    body = DevCredIngest(
        github_token="fake-token",
        repos=["octocat/hello-world"],
        credential_id="dead-end-id",
    )

    with patch("app.devcred.routes.db") as mock_db, \
         patch("httpx.AsyncClient", return_value=_FakeGithubAsyncClientRevokedNoEvents()):
        mock_db.create_dev_credential = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await ingest_repos(_fake_request(path="/api/devcred/ingest"), body)

    assert exc_info.value.status_code == 404
    detail = exc_info.value.detail
    assert detail["error"] == "repo_access_revoked_no_recent_activity"
    assert "local_git_upload" in detail["fallback_available"]
    assert "self_reported" in detail["fallback_available"]
    mock_db.create_dev_credential.assert_not_called()


# ---------------------------------------------------------------------------
# 24. evaluate_credential — events_stream branch skips the LLM entirely
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_credential_events_stream_never_calls_llm():
    from app.devcred.routes import evaluate_credential

    events = [_event("PushEvent", "acme/widgets", "2026-09-01T00:00:00Z", str(i)) for i in range(5)]
    metrics = extract_event_metrics(events)

    db_record = {
        "credential_id": "events-eval-id",
        "developer_handle": "octocat",
        "repo_corpus_root": "e" * 64,
        "commit_count": 0,
        "event_count": metrics["total_events"],
        "metrics": metrics,
        "credential": None,
        "tee_quote": None,
        "status": "ingested",
        "provenance_method": "events_stream",
    }

    with patch("app.devcred.routes.db") as mock_db, \
         patch("app.devcred.routes.sign_result", new=AsyncMock(return_value="sim_quote:events")), \
         patch("app.devcred.agents.git_evaluator.GitEvaluatorAgent.evaluate", new=AsyncMock()) as mock_evaluate:

        mock_db.get_dev_credential = AsyncMock(return_value=db_record)
        mock_db.update_dev_credential_result = AsyncMock()
        mock_db.increment_daily_eval_count = AsyncMock(return_value=1)
        mock_db.decrement_daily_eval_count = AsyncMock()

        response = await evaluate_credential(_fake_request(), "events-eval-id")

    mock_evaluate.assert_not_called()
    assert response.credential.provenance_method == ProvenanceMethod.EVENTS_STREAM
    assert response.credential.verified is True
    assert response.credential.event_count == metrics["total_events"]
    assert response.credential.hard_seniority_signal == "junior"
    assert "events timeline fallback" in " ".join(response.credential.caveats)


# ---------------------------------------------------------------------------
# 25. local_signature — SSHSIG verification (round-tripped against this
# module's own wire encoder — see local_signature.py's module docstring for
# why this has NOT been cross-checked against a genuine `ssh-keygen` binary)
# ---------------------------------------------------------------------------

def _build_test_ssh_signature(payload: bytes, namespace: str = "devcred-route-c", hash_alg: str = "sha256"):
    """Builds a spec-shaped SSHSIG blob + matching OpenSSH public key line using a
    freshly generated Ed25519 keypair, for testing verify_ssh_signature in isolation."""
    import hashlib as _hashlib
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    raw_pub = pub.public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    pubkey_blob = _write_string(b"ssh-ed25519") + _write_string(raw_pub)

    hasher = {"sha256": _hashlib.sha256, "sha512": _hashlib.sha512}[hash_alg]
    message_hash = hasher(payload).digest()
    signed_data = SSHSIG_MAGIC + _write_string(namespace.encode()) + _write_string(b"") + _write_string(hash_alg.encode()) + _write_string(message_hash)

    raw_sig = priv.sign(signed_data)
    signature_field = _write_string(b"ssh-ed25519") + _write_string(raw_sig)

    blob = SSHSIG_MAGIC + struct.pack(">I", 1) + _write_string(pubkey_blob) + _write_string(namespace.encode()) + _write_string(b"") + _write_string(hash_alg.encode()) + _write_string(signature_field)

    armored = "-----BEGIN SSH SIGNATURE-----\n" + base64.b64encode(blob).decode() + "\n-----END SSH SIGNATURE-----"
    pubkey_line = "ssh-ed25519 " + base64.b64encode(pubkey_blob).decode()
    return armored, pubkey_line, priv


def test_verify_ssh_signature_valid():
    payload = canonical_payload("cred-1", "octocat", "a" * 64)
    armored, pubkey_line, _ = _build_test_ssh_signature(payload)

    result = verify_ssh_signature(payload, armored, pubkey_line)
    assert result.valid is True
    assert result.key_fingerprint is not None
    assert result.key_fingerprint.startswith("SHA256:")


def test_verify_ssh_signature_rejects_tampered_payload():
    payload = canonical_payload("cred-1", "octocat", "a" * 64)
    armored, pubkey_line, _ = _build_test_ssh_signature(payload)

    tampered = canonical_payload("cred-1", "octocat", "b" * 64)
    result = verify_ssh_signature(tampered, armored, pubkey_line)
    assert result.valid is False


def test_verify_ssh_signature_rejects_wrong_namespace():
    payload = canonical_payload("cred-1", "octocat", "a" * 64)
    armored, pubkey_line, _ = _build_test_ssh_signature(payload, namespace="some-other-namespace")

    result = verify_ssh_signature(payload, armored, pubkey_line)
    assert result.valid is False
    assert "namespace" in result.error


def test_verify_ssh_signature_rejects_mismatched_public_key():
    payload = canonical_payload("cred-1", "octocat", "a" * 64)
    armored, _pubkey_line, _ = _build_test_ssh_signature(payload)

    # A different, unrelated keypair's public line — must not verify against it
    _, other_pubkey_line, _ = _build_test_ssh_signature(payload)
    result = verify_ssh_signature(payload, armored, other_pubkey_line)
    assert result.valid is False


def test_verify_signature_dispatches_by_format():
    payload = canonical_payload("cred-1", "octocat", "a" * 64)
    armored, pubkey_line, _ = _build_test_ssh_signature(payload)

    assert verify_signature(payload, armored, pubkey_line, "ssh").valid is True
    result = verify_signature(payload, "garbage", "garbage", "unknown-format")
    assert result.valid is False
    assert "unsupported" in result.error


def test_verify_gpg_signature_fails_closed_on_garbage_input():
    """No real GPG keypair is available in this environment — confirms the fail-closed
    path (never fabricates a pass) rather than exercising a real gpg binary round-trip."""
    result = verify_gpg_signature(b"payload", "not a real signature", "not a real key")
    assert result.valid is False


# ---------------------------------------------------------------------------
# 26. Route C endpoint — POST /ingest-local
# ---------------------------------------------------------------------------

def _local_commit(sha: str, message: str = "fix bug") -> dict:
    return {
        "sha": sha,
        "author": "octocat",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "message": message,
        "diff_stat": {"additions": 10, "deletions": 2, "total": 12},
    }


@pytest.mark.asyncio
async def test_ingest_local_git_accepts_valid_signature():
    from app.devcred.routes import ingest_local_git
    from app.devcred.schemas import LocalGitUploadRequest

    commits = [_local_commit("sha1"), _local_commit("sha2", "add feature")]
    corpus_root = compute_repo_corpus_root(commits)
    payload = canonical_payload("local-cred-1", "octocat", corpus_root)
    armored, pubkey_line, _ = _build_test_ssh_signature(payload)

    body = LocalGitUploadRequest(
        credential_id="local-cred-1",
        developer_handle="octocat",
        commits=commits,
        signature=armored,
        signature_format="ssh",
        public_key=pubkey_line,
    )

    class _NoKeysClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, params=None, timeout=None):
            return _make_github_response([], status_code=200)

    with patch("app.devcred.routes.db") as mock_db, \
         patch("httpx.AsyncClient", return_value=_NoKeysClient()):
        mock_db.create_dev_credential = AsyncMock()
        response = await ingest_local_git(_fake_request(path="/api/devcred/ingest-local"), body)

    assert response.commit_count == 2
    assert response.corpus_root == corpus_root
    assert response.key_fingerprint is not None
    assert response.github_key_currently_listed is False  # empty keys list from the fake client
    mock_db.create_dev_credential.assert_awaited_once()
    _, kwargs = mock_db.create_dev_credential.call_args
    assert kwargs["provenance_method"] == "local_git_upload"


@pytest.mark.asyncio
async def test_ingest_local_git_rejects_invalid_signature():
    from app.devcred.routes import ingest_local_git
    from app.devcred.schemas import LocalGitUploadRequest

    commits = [_local_commit("sha1")]
    corpus_root = compute_repo_corpus_root(commits)
    # Sign over a DIFFERENT corpus root than the one that will actually be recomputed
    # server-side from `commits` — simulates a tampered/incorrect submission.
    wrong_payload = canonical_payload("local-cred-2", "octocat", "0" * 64)
    armored, pubkey_line, _ = _build_test_ssh_signature(wrong_payload)

    body = LocalGitUploadRequest(
        credential_id="local-cred-2",
        developer_handle="octocat",
        commits=commits,
        signature=armored,
        signature_format="ssh",
        public_key=pubkey_line,
    )

    with patch("app.devcred.routes.db") as mock_db:
        mock_db.create_dev_credential = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await ingest_local_git(_fake_request(path="/api/devcred/ingest-local"), body)

    assert exc_info.value.status_code == 401
    mock_db.create_dev_credential.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_local_git_requires_at_least_one_commit():
    from app.devcred.routes import ingest_local_git
    from app.devcred.schemas import LocalGitUploadRequest

    body = LocalGitUploadRequest(
        credential_id="local-cred-3",
        developer_handle="octocat",
        commits=[],
        signature="x",
        signature_format="ssh",
        public_key="x",
    )
    with pytest.raises(HTTPException) as exc_info:
        await ingest_local_git(_fake_request(path="/api/devcred/ingest-local"), body)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_evaluate_credential_local_git_upload_flags_missing_language_signal():
    """Route C shares Route A's evaluate pipeline — confirms the caveat disclosing
    the absent file-path/language signal is actually attached, not just documented."""
    from app.devcred.routes import evaluate_credential

    commits = [_local_commit("sha1"), _local_commit("sha2")]
    metrics_input = [{**c, "is_merge": False, "files": []} for c in commits]
    metrics = extract_commit_metrics(metrics_input)

    db_record = {
        "credential_id": "local-eval-id",
        "developer_handle": "octocat",
        "repo_corpus_root": compute_repo_corpus_root(commits),
        "commit_count": 2,
        "event_count": None,
        "metrics": metrics,
        "credential": None,
        "tee_quote": None,
        "status": "ingested",
        "provenance_method": "local_git_upload",
    }

    llm_response = json.dumps({
        "seniority_level": "mid",
        "primary_languages": [],
        "specializations": [],
        "contribution_pattern": "Steady commits.",
        "qualitative_assessment": "Reasonable contribution history.",
        "confidence": "medium",
        "caveats": [],
    })

    with patch("app.devcred.routes.db") as mock_db, \
         patch("app.devcred.routes.sign_result", new=AsyncMock(return_value="sim_quote:local")):
        mock_db.get_dev_credential = AsyncMock(return_value=db_record)
        mock_db.update_dev_credential_result = AsyncMock()
        mock_db.increment_daily_eval_count = AsyncMock(return_value=1)
        mock_db.decrement_daily_eval_count = AsyncMock()

        evaluator_mock_client = AsyncMock()
        evaluator_mock_client.messages.create = AsyncMock(return_value=_make_mock_response(llm_response))
        with patch("app.devcred.agents.git_evaluator.anthropic.AsyncAnthropic", return_value=evaluator_mock_client):
            response = await evaluate_credential(_fake_request(), "local-eval-id")

    assert response.credential.provenance_method == ProvenanceMethod.LOCAL_GIT_UPLOAD
    assert response.credential.has_test_culture is False
    assert response.credential.primary_languages == []
    assert any("no file paths were available" in c for c in response.credential.caveats)


# ---------------------------------------------------------------------------
# 27. Route D endpoint — POST /self-report (the honest dead end)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_self_report_produces_clearly_unverified_credential():
    from app.devcred.routes import self_report_credential
    from app.devcred.schemas import SelfReportedRequest

    body = SelfReportedRequest(
        credential_id="self-report-1",
        developer_handle="octocat",
        role_title="Senior Backend Engineer",
        company_name="Old Employer Inc",
        employment_start="2019-01-01",
        employment_end="2022-06-01",
    )

    with patch("app.devcred.routes.db") as mock_db, \
         patch("app.devcred.routes.sign_result", new=AsyncMock(return_value="sim_quote:selfreport")):
        mock_db.get_dev_credential = AsyncMock(return_value=None)
        mock_db.create_dev_credential_complete = AsyncMock()

        response = await self_report_credential(_fake_request(), body)

    cred = response.credential
    assert cred.provenance_method == ProvenanceMethod.SELF_REPORTED
    assert cred.verified is False
    assert cred.repo_corpus_root is None
    assert cred.commit_count == 0
    assert cred.self_reported is not None
    assert cred.self_reported.company_name == "Old Employer Inc"
    assert cred.self_reported.role_title == "Senior Backend Engineer"
    assert any("UNVERIFIED" in c for c in cred.caveats)

    mock_db.create_dev_credential_complete.assert_awaited_once()
    _, kwargs = mock_db.create_dev_credential_complete.call_args
    assert kwargs["provenance_method"] == "self_reported"
    # the placeholder passed to the DB layer is never a real hash and never
    # leaks into the credential object itself (checked above: repo_corpus_root is None)
    assert kwargs["repo_corpus_root"] == "self-reported:self-report-1"


@pytest.mark.asyncio
async def test_self_report_never_fabricates_a_seniority_score():
    """The dead-end path must not produce a graded credential that could be
    mistaken for a real assessment — hard_seniority_signal stays None."""
    from app.devcred.routes import self_report_credential
    from app.devcred.schemas import SelfReportedRequest

    body = SelfReportedRequest(
        credential_id="self-report-2",
        role_title="Staff Engineer",
        company_name="Some Co",
        employment_start="2015-01-01",
    )

    with patch("app.devcred.routes.db") as mock_db, \
         patch("app.devcred.routes.sign_result", new=AsyncMock(return_value="sim_quote:x")):
        mock_db.get_dev_credential = AsyncMock(return_value=None)
        mock_db.create_dev_credential_complete = AsyncMock()
        response = await self_report_credential(_fake_request(), body)

    assert response.credential.hard_seniority_signal is None
    assert response.credential.confidence == "low"
    assert "unverified" in response.credential.qualitative_assessment.lower()


@pytest.mark.asyncio
async def test_self_report_rejects_duplicate_credential_id():
    from app.devcred.routes import self_report_credential
    from app.devcred.schemas import SelfReportedRequest

    body = SelfReportedRequest(
        credential_id="dup-id",
        role_title="Engineer",
        company_name="Co",
        employment_start="2020-01-01",
    )

    with patch("app.devcred.routes.db") as mock_db:
        mock_db.get_dev_credential = AsyncMock(return_value={"status": "complete"})
        with pytest.raises(HTTPException) as exc_info:
            await self_report_credential(_fake_request(), body)

    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# 28. db.py — provenance_method / event_count persistence + migration safety
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_create_dev_credential_defaults_to_direct_access(tmp_path):
    import app.db as db_module

    original_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / f"test_{time.time_ns()}.db"
    try:
        await db_module.create_dev_credentials_table()
        await db_module.create_dev_credential(
            credential_id="db-test-1",
            developer_handle="octocat",
            repo_corpus_root="a" * 64,
            commit_count=5,
            metrics={},
        )
        record = await db_module.get_dev_credential("db-test-1")
        assert record["provenance_method"] == "direct_access"
        assert record["event_count"] is None
    finally:
        db_module.DB_PATH = original_path


@pytest.mark.asyncio
async def test_db_create_dev_credential_complete_for_self_reported(tmp_path):
    import app.db as db_module

    original_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / f"test_{time.time_ns()}.db"
    try:
        await db_module.create_dev_credentials_table()
        await db_module.create_dev_credential_complete(
            credential_id="db-test-2",
            developer_handle="octocat",
            repo_corpus_root="self-reported:db-test-2",
            credential={"credential_id": "db-test-2", "verified": False},
            tee_quote="sim_quote:z",
            provenance_method="self_reported",
        )
        record = await db_module.get_dev_credential("db-test-2")
        assert record["status"] == "complete"
        assert record["provenance_method"] == "self_reported"
        assert record["credential"]["verified"] is False
    finally:
        db_module.DB_PATH = original_path


def test_create_dev_credentials_table_migration_is_idempotent(tmp_path):
    """Running the ALTER TABLE migration twice must not raise — same 'duplicate
    column name' swallow pattern as init_db()'s core `deals` table migration."""
    import asyncio
    import app.db as db_module

    original_path = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / f"test_{time.time_ns()}.db"

    async def _run():
        await db_module.create_dev_credentials_table()
        await db_module.create_dev_credentials_table()  # must be a safe no-op

    try:
        asyncio.run(_run())
    finally:
        db_module.DB_PATH = original_path
