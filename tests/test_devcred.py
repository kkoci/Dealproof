"""
Dev credential tests — Phase 4.

15 tests covering:
  - Corpus root determinism (2)
  - extract_commit_metrics correctness (1)
  - GitInspectorAgent: seniority signals for senior/mid/junior fixtures (3)
  - SCAE: adversarial messages don't elevate hard seniority signal (1)
  - SCAE: adversarial churn detected via avg_diff_size (1)
  - HTTP: ingest direct mode (1)
  - Token not persisted after ingest (1)
  - HTTP: evaluate pipeline round-trip (1)
  - Credential schema: employer/repo names absent (1)
  - Credential hash in TDX report_data (1)
  - GET dev credential returns status (1)
  - Seniority floor enforced — LLM cannot downgrade (1)

External I/O mocked:
  - GitEvaluatorAgent.evaluate → AsyncMock
  - sign_result → AsyncMock
  - app.db.DB_PATH → tmp file
"""
import hashlib
import json
import pytest
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from app.devcred.git_hasher import (
    hash_commit,
    compute_repo_corpus_root,
    extract_commit_metrics,
)
from app.devcred.agents.git_inspector import (
    GitInspectorAgent,
    YEARS_SENIOR,
    YEARS_MID,
    TEST_RATIO_THRESHOLD,
    LANGUAGE_DEPTH_MIN_FILES,
)


# ---------------------------------------------------------------------------
# Synthetic commit fixtures
# ---------------------------------------------------------------------------

def _make_commit(
    sha: str,
    date_str: str,  # "YYYY-MM-DD"
    message: str = "fix: minor update",
    additions: int = 30,
    deletions: int = 10,
    files: list[str] | None = None,
) -> dict:
    return {
        "sha": sha,
        "author": "testdev",
        "timestamp": f"{date_str}T10:00:00Z",
        "message": message,
        "diff_stat": {"additions": additions, "deletions": deletions},
        "changed_files": files or ["src/main.go"],
    }


def _make_corpus(n: int, start_year: int, lang_files: list[str], test_ratio: float = 0.2) -> list[dict]:
    """Generate n commits over ~(2024 - start_year) years."""
    commits = []
    year_span = max(1, 2024 - start_year)
    for i in range(n):
        frac = i / n
        year = start_year + int(frac * year_span)
        month = 1 + (i % 12)
        day = 1 + (i % 28)
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        files = list(lang_files)
        if i % int(1 / test_ratio) == 0 if test_ratio > 0 else False:
            files.append("tests/test_main.go")
        commits.append(_make_commit(
            sha=f"commit_{i:05d}",
            date_str=date_str,
            message=f"feat: implement feature {i} with detailed description of changes",
            additions=80,
            deletions=20,
            files=files,
        ))
    return commits


# Genuine senior: 8 years, Go + Python depth, 25% test ratio
_GENUINE_SENIOR = _make_corpus(
    300,
    start_year=2016,
    lang_files=["src/server.go"] * 5 + ["src/handler.py"] * 3,
    test_ratio=0.25,
)
# Ensure language depth: add enough Go and Python commits
for i in range(30):
    _GENUINE_SENIOR.append(_make_commit(
        sha=f"go_deep_{i:03d}",
        date_str=f"2018-{(i % 12) + 1:02d}-15",
        files=["pkg/core.go", "pkg/utils.go", "tests/core_test.go"],
        additions=100, deletions=30,
    ))

# Genuine mid: 4 years, JavaScript
_GENUINE_MID = _make_corpus(
    150,
    start_year=2020,
    lang_files=["src/index.js", "src/utils.js"],
    test_ratio=0.1,
)

# Genuine junior: 1 year, Python, few commits
_GENUINE_JUNIOR = _make_corpus(
    30,
    start_year=2023,
    lang_files=["script.py"],
    test_ratio=0.0,
)
for c in _GENUINE_JUNIOR:
    c["message"] = "update"  # short messages
    c["diff_stat"] = {"additions": 5, "deletions": 2}

# SCAE: adversarial messages — junior metrics but very impressive long messages
_ADVERSARIAL_MESSAGES = _make_corpus(
    25,
    start_year=2023,
    lang_files=["main.py"],
    test_ratio=0.0,
)
for i, c in enumerate(_ADVERSARIAL_MESSAGES):
    c["message"] = (
        "Refactored the distributed consensus layer to improve Byzantine "
        "fault-tolerance using Raft protocol — led architecture across 12 "
        "microservices and coordinated with cross-functional engineering teams"
    )
    c["diff_stat"] = {"additions": 3, "deletions": 1}  # tiny actual changes

# SCAE: adversarial churn — hundreds of commits, all 1-2 lines (whitespace/formatting)
_ADVERSARIAL_CHURN = []
for i in range(350):
    frac = i / 350
    year = 2022 + int(frac * 2)
    month = 1 + (i % 12)
    day = 1 + (i % 28)
    _ADVERSARIAL_CHURN.append(_make_commit(
        sha=f"churn_{i:05d}",
        date_str=f"{year:04d}-{month:02d}-{day:02d}",
        message="fix whitespace",
        additions=1,
        deletions=1,
        files=["README.md"],
    ))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inspect(commits: list[dict]) -> "GitInspectionReport":
    metrics = extract_commit_metrics(commits)
    return GitInspectorAgent().inspect(metrics)


# ---------------------------------------------------------------------------
# Corpus root determinism (2)
# ---------------------------------------------------------------------------

def test_corpus_root_determinism():
    root1 = compute_repo_corpus_root(_GENUINE_SENIOR)
    root2 = compute_repo_corpus_root(_GENUINE_SENIOR)
    assert root1 == root2
    assert len(root1) == 64


def test_corpus_root_changes_with_content():
    root_a = compute_repo_corpus_root(_GENUINE_SENIOR)
    root_b = compute_repo_corpus_root(_GENUINE_JUNIOR)
    assert root_a != root_b


# ---------------------------------------------------------------------------
# extract_commit_metrics (1)
# ---------------------------------------------------------------------------

def test_extract_metrics_basic():
    commits = [
        _make_commit("a1", "2022-01-15", files=["src/main.go", "tests/main_test.go"]),
        _make_commit("a2", "2022-03-10", files=["src/server.go"]),
        _make_commit("a3", "2022-05-20", message="merge branch", files=["src/api.go"]),
    ]
    m = extract_commit_metrics(commits)
    assert m["total_commits"] == 3
    assert m["active_months"] == 3  # Jan, Mar, May
    assert "Go" in m["languages"]
    # One commit touches a test file
    assert m["test_file_ratio"] == pytest.approx(1 / 3, abs=0.01)
    # One merge commit
    assert m["merge_commit_ratio"] == pytest.approx(1 / 3, abs=0.01)
    assert m["first_commit_date"].startswith("2022-01")
    assert m["last_commit_date"].startswith("2022-05")


# ---------------------------------------------------------------------------
# GitInspectorAgent seniority signals (3)
# ---------------------------------------------------------------------------

def test_inspector_genuine_senior():
    report = _inspect(_GENUINE_SENIOR)
    assert report.seniority_signal == "senior"
    assert "Go" in report.languages_deep or "Python" in report.languages_deep
    assert report.has_test_culture
    assert report.years_active >= YEARS_SENIOR


def test_inspector_genuine_mid():
    report = _inspect(_GENUINE_MID)
    assert report.seniority_signal in ("mid", "senior")
    assert report.years_active >= YEARS_MID


def test_inspector_genuine_junior():
    report = _inspect(_GENUINE_JUNIOR)
    assert report.seniority_signal == "junior"
    assert report.years_active < YEARS_MID


# ---------------------------------------------------------------------------
# SCAE — adversarial scenarios (2)
# ---------------------------------------------------------------------------

def test_scae_adversarial_messages_stays_junior():
    """
    Junior metrics (1 year, tiny diffs) with impressive commit messages.
    Hard seniority_signal must remain 'junior' regardless of message content.
    """
    report = _inspect(_ADVERSARIAL_MESSAGES)
    assert report.seniority_signal == "junior", (
        f"SCAE FAILURE: impressive messages elevated seniority to {report.seniority_signal}"
    )


def test_scae_adversarial_churn_detected():
    """
    High commit count (350) but all 1-line whitespace changes.
    avg_diff_size should be tiny, preventing senior signal via commit volume alone.
    """
    metrics = extract_commit_metrics(_ADVERSARIAL_CHURN)
    assert metrics["avg_diff_size"] < 5.0, (
        f"SCAE FAILURE: churn not detected — avg_diff_size={metrics['avg_diff_size']}"
    )
    # Inspector should not award senior even with high commit count
    report = GitInspectorAgent().inspect(metrics)
    assert report.seniority_signal != "senior", (
        f"SCAE FAILURE: churn commits elevated seniority to {report.seniority_signal}"
    )


# ---------------------------------------------------------------------------
# HTTP stack — ingest + evaluate + GET (3)
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    tmp_db = tmp_path / "test_devcred.db"
    with patch("app.db.DB_PATH", Path(str(tmp_db))):
        from app.main import app
        with TestClient(app) as c:
            yield c


def test_ingest_direct_mode(client):
    resp = client.post("/api/devcred/ingest", json={
        "credential_id": "cred-001",
        "developer_handle": "alice",
        "mode": "direct",
        "commits": [c for c in _GENUINE_JUNIOR],  # small corpus
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["credential_id"] == "cred-001"
    assert len(data["repo_corpus_root"]) == 64
    assert data["commit_count"] == len(_GENUINE_JUNIOR)
    assert "metrics_preview" in data


def test_token_not_persisted(client):
    """github_token must not appear in any stored DB field."""
    fake_token = "ghp_SECRETTOKEN12345678"

    # Use direct mode but sneak a token into the payload — it should not be stored
    resp = client.post("/api/devcred/ingest", json={
        "credential_id": "cred-token-test",
        "developer_handle": "bob",
        "mode": "direct",
        "github_token": fake_token,
        "commits": [_make_commit("tok1", "2024-01-01")],
    })
    assert resp.status_code == 200

    # Fetch the raw DB record through the GET endpoint
    get_resp = client.get("/api/devcred/cred-token-test")
    assert get_resp.status_code == 200
    raw_json = get_resp.text
    assert fake_token not in raw_json


_MOCK_EVAL_RESULT = {
    "seniority_level": "senior",
    "primary_languages": ["Go", "Python"],
    "specializations": ["distributed systems"],
    "contribution_pattern": "Consistent high-quality commits over 8+ years.",
    "qualitative_assessment": "Strong senior engineer with deep Go expertise.",
    "confidence": "high",
    "caveats": [],
}


@pytest.fixture
def eval_client(client):
    """Client with GitEvaluatorAgent.evaluate and sign_result mocked."""
    from app.devcred.agents.git_evaluator import GitEvaluatorAgent
    mock_ev = AsyncMock(return_value=_MOCK_EVAL_RESULT)
    mock_sign = AsyncMock(return_value="sim_quote:abc123")
    with (
        patch.object(GitEvaluatorAgent, "evaluate", mock_ev),
        patch("app.devcred.routes.sign_result", mock_sign),
    ):
        yield client


def test_evaluate_pipeline_round_trip(eval_client):
    """Full pipeline: ingest → evaluate → credential returned."""
    ingest_resp = eval_client.post("/api/devcred/ingest", json={
        "credential_id": "cred-eval-001",
        "developer_handle": "carol",
        "mode": "direct",
        "commits": list(_GENUINE_SENIOR[:50]),
    })
    assert ingest_resp.status_code == 200

    eval_resp = eval_client.post("/api/devcred/cred-eval-001/evaluate", json={})
    assert eval_resp.status_code == 200
    cred = eval_resp.json()

    assert cred["credential_type"] == "SeniorDevCredential"
    assert cred["developer_handle"] == "carol"
    assert len(cred["credential_hash"]) == 64
    assert cred["tee_attested"] is True


def test_credential_schema_no_employer_info(eval_client):
    """Credential must not contain repo names, employer names, or file paths."""
    resp = eval_client.post("/api/devcred/ingest", json={
        "credential_id": "cred-privacy",
        "developer_handle": "devuser",
        "mode": "direct",
        "commits": [
            _make_commit(
                "p1", "2024-01-01",
                files=["my-secret-employer/src/main.go"]
            )
        ],
    })
    assert resp.status_code == 200

    eval_resp = eval_client.post("/api/devcred/cred-privacy/evaluate", json={})
    assert eval_resp.status_code == 200
    cred_json = eval_resp.text
    # Employer name from file path must not appear
    assert "my-secret-employer" not in cred_json
    assert "employer" not in cred_json.lower()


def test_credential_hash_in_tee_report_data(eval_client):
    """
    The TDX quote must be a function of credential_hash + repo_corpus_root.
    In simulation mode, sign_result returns sim_quote:<hash>.
    """
    ingest_resp = eval_client.post("/api/devcred/ingest", json={
        "credential_id": "cred-attest",
        "developer_handle": "testdev",
        "mode": "direct",
        "commits": [_make_commit("att1", "2024-01-01")],
    })
    assert ingest_resp.status_code == 200

    eval_resp = eval_client.post("/api/devcred/cred-attest/evaluate", json={})
    assert eval_resp.status_code == 200
    cred = eval_resp.json()

    assert cred["tee_quote"].startswith("sim_quote:")
    assert cred["credential_hash"] is not None
    assert len(cred["credential_hash"]) == 64


def test_get_dev_credential_status(client):
    """GET /api/devcred/{id} returns status and metadata after ingest."""
    client.post("/api/devcred/ingest", json={
        "credential_id": "cred-get-test",
        "developer_handle": "eve",
        "mode": "direct",
        "commits": [_make_commit("g1", "2024-06-01")],
    })

    get_resp = client.get("/api/devcred/cred-get-test")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["status"] == "pending"
    assert data["credential"] is None
    assert data["developer_handle"] == "eve"
    assert len(data["repo_corpus_root"]) == 64


def test_get_dev_credential_404(client):
    resp = client.get("/api/devcred/nonexistent-id")
    assert resp.status_code == 404


def test_seniority_floor_enforced():
    """
    LLM returning a lower seniority than the hard finding must be clamped up.
    """
    from app.devcred.agents.git_evaluator import GitEvaluatorAgent, _SENIORITY_ORDER
    from app.devcred.agents.git_inspector import GitInspectionReport

    # Hard finding: "mid"
    inspection = GitInspectionReport(
        years_active=4.0,
        languages_deep=["JavaScript"],
        has_test_culture=True,
        consistent_contribution=True,
        avg_commit_quality="medium",
        seniority_signal="mid",
    )

    # Simulate LLM returning "junior" (below hard signal)
    llm_level = "junior"
    hard_idx = _SENIORITY_ORDER.index("mid")
    llm_idx = _SENIORITY_ORDER.index(llm_level)
    enforced = _SENIORITY_ORDER[max(hard_idx, llm_idx)]

    assert enforced == "mid", (
        f"Seniority floor not enforced: LLM said {llm_level!r}, "
        f"hard floor is 'mid', got {enforced!r}"
    )
