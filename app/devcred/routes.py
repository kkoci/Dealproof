"""
Developer credential routes — /api/devcred/.

Phase 1: POST /api/devcred/ingest — fetch commits, extract metrics, compute corpus root.
Phase 3: POST /api/devcred/{credential_id}/evaluate — full pipeline → SeniorDevCredential + TDX quote.
         GET  /api/devcred/{credential_id}           — status + credential if complete.

Privacy constraints:
  - github_token: used in-memory during this request, never written to disk or DB
  - repo names: hashed into corpus_root only, never stored in DB
  - employer names: never appear in the system
  - raw diffs + file paths: not stored, only aggregate metrics
"""
import hashlib
import json
import math
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import app.db as db
from app.devcred.git_hasher import compute_repo_corpus_root, extract_commit_metrics
from app.devcred.agents.git_inspector import GitInspectorAgent, GitInspectionReport
from app.devcred.agents.git_evaluator import GitEvaluatorAgent, GitEvaluation
from app.devcred.schemas import (
    SeniorDevCredential,
    DevCredEvaluateResponse,
    DevCredStatusResponse,
)
from app.tee.attestation import sign_result

router = APIRouter(prefix="/api/devcred", tags=["devcred"])

GITHUB_API = "https://api.github.com"
MAX_COMMITS_PER_REPO = 300
DETAIL_SAMPLE_SIZE = 50  # commits fetched individually for file/diff details


class DevCredIngest(BaseModel):
    github_token: str = Field(..., description="Read-only GitHub PAT — used in-memory only, never stored")
    repos: list[str] = Field(..., min_length=1, description="List of 'owner/repo' strings")
    credential_id: str = Field(..., description="UUID for this credential (caller-generated)")


class DevCredIngestResponse(BaseModel):
    credential_id: str
    corpus_root: str
    commit_count: int
    repo_count: int
    metrics_preview: dict


def _github_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _fetch_github_username(token: str, client: httpx.AsyncClient) -> str:
    """Return the GitHub login for the token owner. Non-fatal — returns 'unknown' on error."""
    try:
        resp = await client.get(
            f"{GITHUB_API}/user",
            headers=_github_headers(token),
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("login", "unknown")
    except Exception:
        pass
    return "unknown"


async def _fetch_commit_list(token: str, repo: str, client: httpx.AsyncClient) -> list[dict]:
    """
    Paginate up to MAX_COMMITS_PER_REPO commits from the GitHub commits list endpoint.
    Returns lightweight commit dicts: sha, author, timestamp, message, is_merge.
    """
    headers = _github_headers(token)
    commits: list[dict] = []
    page = 1

    while len(commits) < MAX_COMMITS_PER_REPO:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/commits",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=30.0,
        )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Repo not found or token lacks access: {repo}",
            )
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="GitHub token invalid or expired")
        resp.raise_for_status()

        page_data = resp.json()
        if not page_data:
            break

        for item in page_data:
            commit_obj = item.get("commit", {})
            author = commit_obj.get("author", {})
            commits.append({
                "sha": item["sha"],
                "author": author.get("name"),
                "timestamp": author.get("date"),
                "message": commit_obj.get("message", ""),
                "is_merge": len(item.get("parents", [])) > 1,
                "diff_stat": None,
                "files": [],
            })

        if len(page_data) < 100:
            break
        page += 1

    return commits[:MAX_COMMITS_PER_REPO]


async def _enrich_sample_with_details(
    token: str, repo: str, commits: list[dict], client: httpx.AsyncClient
) -> list[dict]:
    """
    Fetch full commit details (stats + file paths) for an evenly-spaced sample.
    Enrichment is best-effort — failures are silently skipped.
    """
    headers = _github_headers(token)
    step = max(1, math.ceil(len(commits) / DETAIL_SAMPLE_SIZE))
    sample_indices = range(0, len(commits), step)

    for idx in sample_indices:
        sha = commits[idx]["sha"]
        try:
            resp = await client.get(
                f"{GITHUB_API}/repos/{repo}/commits/{sha}",
                headers=headers,
                timeout=30.0,
            )
            if resp.status_code != 200:
                continue
            detail = resp.json()
            stats = detail.get("stats", {})
            commits[idx]["diff_stat"] = {
                "additions": stats.get("additions", 0),
                "deletions": stats.get("deletions", 0),
                "total": stats.get("total", 0),
            }
            # store only filename + line counts, not content
            commits[idx]["files"] = [
                {
                    "filename": f.get("filename", ""),
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0),
                }
                for f in detail.get("files", [])
            ]
        except Exception:
            pass

    return commits


@router.post("/ingest", response_model=DevCredIngestResponse)
async def ingest_repos(body: DevCredIngest) -> DevCredIngestResponse:
    """
    Fetch commits from GitHub, extract deterministic metrics, compute corpus root.
    GitHub token is used in-memory only — never written to disk or database.
    """
    for repo in body.repos:
        if "/" not in repo or repo.startswith("/") or repo.endswith("/"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid repo format (expected owner/repo): {repo}",
            )

    all_commits: list[dict] = []
    developer_handle = "unknown"

    async with httpx.AsyncClient() as client:
        developer_handle = await _fetch_github_username(body.github_token, client)

        for repo in body.repos:
            commits = await _fetch_commit_list(body.github_token, repo, client)
            commits = await _enrich_sample_with_details(body.github_token, repo, commits, client)
            all_commits.extend(commits)

    # token is no longer referenced after the async block above

    if not all_commits:
        raise HTTPException(status_code=400, detail="No commits found across specified repos")

    # canonical commits for corpus root — repo names not included
    canonical_commits = [
        {
            "sha": c["sha"],
            "author": c["author"],
            "timestamp": c["timestamp"],
            "message": c["message"],
            "diff_stat": c["diff_stat"],
        }
        for c in all_commits
    ]

    corpus_root = compute_repo_corpus_root(canonical_commits)
    metrics = extract_commit_metrics(all_commits)

    # persist — token never written
    await db.create_dev_credential(
        credential_id=body.credential_id,
        developer_handle=developer_handle,
        repo_corpus_root=corpus_root,
        commit_count=len(all_commits),
        metrics=metrics,
    )

    metrics_preview = {
        "total_commits": metrics["total_commits"],
        "active_months": metrics["active_months"],
        "languages": metrics["languages"],
        "avg_diff_size": round(metrics["avg_diff_size"], 1),
        "test_file_ratio": round(metrics["test_file_ratio"], 3),
        "merge_commit_ratio": round(metrics["merge_commit_ratio"], 3),
        "first_commit_date": metrics["first_commit_date"],
        "last_commit_date": metrics["last_commit_date"],
    }

    return DevCredIngestResponse(
        credential_id=body.credential_id,
        corpus_root=corpus_root,
        commit_count=len(all_commits),
        repo_count=len(body.repos),
        metrics_preview=metrics_preview,
    )


# ---------------------------------------------------------------------------
# Phase 3 helpers
# ---------------------------------------------------------------------------

def _hash_credential(cred_fields: dict) -> str:
    """SHA-256 of canonical credential JSON — embedded in TDX report_data."""
    return hashlib.sha256(
        json.dumps(cred_fields, sort_keys=True).encode()
    ).hexdigest()


def _fallback_evaluation(hard: GitInspectionReport, metrics: dict) -> GitEvaluation:
    """Used when GitEvaluatorAgent fails — produce a minimal evaluation from hard findings."""
    languages = list(metrics.get("languages", {}).keys())
    return GitEvaluation(
        seniority_level=hard.seniority_signal,
        primary_languages=hard.languages_deep or languages[:3],
        specializations=[],
        contribution_pattern=(
            f"{hard.avg_commit_quality.title()}-quality commits over {hard.years_active:.1f} years."
        ),
        qualitative_assessment=(
            "LLM evaluation unavailable; assessment derived from deterministic metrics only."
        ),
        confidence="low",
        caveats=["LLM evaluation failed — hard findings only", "manual review recommended"],
    )


# ---------------------------------------------------------------------------
# Phase 3 endpoints
# ---------------------------------------------------------------------------

@router.post("/{credential_id}/evaluate", response_model=DevCredEvaluateResponse)
async def evaluate_credential(credential_id: str) -> DevCredEvaluateResponse:
    """
    Run the full two-layer analysis pipeline on an ingested corpus.

    Pipeline:
      1. GitInspectorAgent.inspect(metrics) → hard findings (deterministic)
      2. GitEvaluatorAgent.evaluate(metrics, hard_findings) → qualitative fields
      3. Build SeniorDevCredential
      4. credential_hash = SHA-256(credential fields)
      5. Embed {credential_hash, repo_corpus_root} in TDX report_data
      6. Persist to dev_credentials, return credential + TDX quote
    """
    record = await db.get_dev_credential(credential_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Credential not found: {credential_id}")
    if record["status"] not in ("ingested", "pending"):
        raise HTTPException(
            status_code=409,
            detail=f"Credential already evaluated (status={record['status']})",
        )

    metrics: dict = record["metrics"] or {}
    repo_corpus_root: str = record["repo_corpus_root"]
    developer_handle: str = record["developer_handle"] or "unknown"
    commit_count: int = record["commit_count"] or 0

    # Step 1 — deterministic hard findings
    inspector = GitInspectorAgent()
    hard = inspector.inspect(metrics)

    # Step 2 — LLM qualitative evaluation (non-fatal)
    evaluator = GitEvaluatorAgent()
    evaluation = await evaluator.evaluate(metrics, hard)
    if evaluation is None:
        evaluation = _fallback_evaluation(hard, metrics)

    # Step 3 — build credential (credential_hash placeholder)
    issued_at = datetime.now(timezone.utc).isoformat()
    cred_fields = {
        "credential_type": "SeniorDevCredential",
        "credential_id": credential_id,
        "developer_handle": developer_handle,
        "repo_corpus_root": repo_corpus_root,
        "commit_count": commit_count,
        "years_active": hard.years_active,
        "hard_seniority_signal": hard.seniority_signal,
        "seniority_level": evaluation.seniority_level,
        "primary_languages": evaluation.primary_languages,
        "specializations": evaluation.specializations,
        "has_test_culture": hard.has_test_culture,
        "qualitative_assessment": evaluation.qualitative_assessment,
        "confidence": evaluation.confidence,
        "caveats": evaluation.caveats,
        "issued_at": issued_at,
    }

    # Step 4 — credential_hash over all fields (before tee_attested is set)
    credential_hash = _hash_credential(cred_fields)
    cred_fields["credential_hash"] = credential_hash

    # Step 5 — TDX attestation: bind credential_hash + corpus_root
    tee_quote = await sign_result({
        "credential_hash": credential_hash,
        "repo_corpus_root": repo_corpus_root,
    })
    tee_attested = bool(tee_quote)
    cred_fields["tee_attested"] = tee_attested

    credential = SeniorDevCredential(**cred_fields)

    # Step 6 — persist
    await db.update_dev_credential_result(
        credential_id=credential_id,
        credential=cred_fields,
        tee_quote=tee_quote,
    )

    return DevCredEvaluateResponse(
        credential_id=credential_id,
        credential=credential,
        tee_quote=tee_quote,
        tee_attested=tee_attested,
    )


@router.get("/{credential_id}", response_model=DevCredStatusResponse)
async def get_credential_status(credential_id: str) -> DevCredStatusResponse:
    """Return current status and credential (if evaluation is complete)."""
    record = await db.get_dev_credential(credential_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Credential not found: {credential_id}")

    credential = None
    if record["credential"]:
        credential = SeniorDevCredential(**record["credential"])

    return DevCredStatusResponse(
        credential_id=credential_id,
        status=record["status"],
        credential=credential,
        tee_quote=record["tee_quote"],
    )
