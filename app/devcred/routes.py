"""
Dev credential routes — POST /api/devcred/ingest,
POST /api/devcred/{id}/evaluate, GET /api/devcred/{id}.

Privacy constraints (non-negotiable):
  - github_token: used in-memory, never written to disk or DB
  - repo names: hashed into corpus_root, never stored in credential
  - employer names: never appear anywhere
  - raw diffs: not stored — only aggregate metrics
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

import app.db as db
from app.devcred.git_hasher import (
    compute_repo_corpus_root,
    extract_commit_metrics,
)
from app.devcred.agents.git_inspector import GitInspectorAgent
from app.devcred.agents.git_evaluator import GitEvaluatorAgent
from app.devcred.schemas import (
    DevCredIngestRequest,
    DevCredEvaluateRequest,
    SeniorDevCredential,
)
from app.tee.attestation import sign_result

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/devcred", tags=["devcred"])


# ---------------------------------------------------------------------------
# GitHub API helper — token used in-memory, never persisted
# ---------------------------------------------------------------------------

async def _fetch_github_commits(token: str, repos: list[str]) -> tuple[list[dict], str]:
    """
    Fetch commits from GitHub API. Returns (commits, developer_handle).
    Token is used here and discarded — not stored.
    Repo names appear only in the API call, not in the returned commits.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    all_commits: list[dict] = []
    developer_handle = ""

    async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:
        # Resolve the GitHub username (for credential, not for corpus)
        try:
            user_resp = await client.get("https://api.github.com/user")
            if user_resp.status_code == 200:
                developer_handle = user_resp.json().get("login", "")
        except Exception:
            pass

        for repo in repos:
            page = 1
            while True:
                try:
                    resp = await client.get(
                        f"https://api.github.com/repos/{repo}/commits",
                        params={"per_page": 100, "page": page},
                    )
                    if resp.status_code != 200:
                        logger.warning(f"GitHub API error {resp.status_code} for {repo}")
                        break
                    items = resp.json()
                    if not items:
                        break
                    for item in items:
                        c = item.get("commit", {})
                        author_info = c.get("author", {})
                        all_commits.append({
                            "sha": item["sha"],
                            "author": author_info.get("name", ""),
                            "timestamp": author_info.get("date", ""),
                            "message": c.get("message", ""),
                            "diff_stat": {},        # not available from list endpoint
                            "changed_files": [],    # not available from list endpoint
                        })
                    page += 1
                    if len(items) < 100:
                        break
                except Exception as exc:
                    logger.warning(f"Failed fetching {repo} page {page}: {exc}")
                    break

    return all_commits, developer_handle


# ---------------------------------------------------------------------------
# POST /api/devcred/ingest
# ---------------------------------------------------------------------------

@router.post("/ingest")
async def ingest_dev_cred(payload: DevCredIngestRequest) -> dict:
    """
    Ingest commit history and compute a corpus root.

    Modes:
      direct  — commits list in request body (tests, demo)
      github  — fetch from GitHub API using token (token never stored)

    Returns corpus_root, commit_count, metrics_preview, credential_id.
    """
    credential_id = payload.credential_id or str(uuid.uuid4())
    developer_handle = payload.developer_handle

    if payload.mode == "github":
        if not payload.github_token:
            raise HTTPException(status_code=400, detail="github_token required for github mode")
        if not payload.repos:
            raise HTTPException(status_code=400, detail="repos required for github mode")
        commits, resolved_handle = await _fetch_github_commits(
            payload.github_token, payload.repos
        )
        if not developer_handle and resolved_handle:
            developer_handle = resolved_handle
    else:
        # direct mode
        commits = payload.commits

    if not commits:
        raise HTTPException(status_code=400, detail="No commits found — cannot compute corpus root")

    corpus_root = compute_repo_corpus_root(commits)
    metrics = extract_commit_metrics(commits)

    await db.create_dev_cred_record(
        credential_id=credential_id,
        developer_handle=developer_handle,
        corpus_root=corpus_root,
        commit_count=len(commits),
        metrics=metrics,
    )

    return {
        "credential_id": credential_id,
        "repo_corpus_root": corpus_root,
        "commit_count": len(commits),
        "metrics_preview": metrics,
    }


# ---------------------------------------------------------------------------
# POST /api/devcred/{credential_id}/evaluate
# ---------------------------------------------------------------------------

@router.post("/{credential_id}/evaluate")
async def evaluate_dev_cred(
    credential_id: str,
    payload: DevCredEvaluateRequest | None = None,
) -> dict:
    """
    Run two-layer analysis and issue a SeniorDevCredential with TDX attestation.

    Layer 1: GitInspectorAgent (deterministic) — hard seniority floor
    Layer 2: GitEvaluatorAgent (LLM) — qualitative context; may raise seniority only
    """
    record = await db.get_dev_cred(credential_id)
    if record is None:
        raise HTTPException(status_code=404, detail="credential_id not found")

    if record["status"] == "evaluated" and record["credential"]:
        return record["credential"]

    metrics = record["metrics"]
    developer_handle = (
        (payload.developer_handle if payload else None)
        or record.get("developer_handle")
        or "unknown"
    )

    # Layer 1 — deterministic hard findings
    inspection = GitInspectorAgent().inspect(metrics)

    # Layer 2 — LLM qualitative layer (non-fatal: falls back to hard findings)
    evaluator = GitEvaluatorAgent()
    eval_result = await evaluator.evaluate(metrics, inspection, developer_handle)

    if eval_result:
        seniority_level = eval_result.get("seniority_level", inspection.seniority_signal)
        primary_languages = eval_result.get("primary_languages", inspection.languages_deep)
        specializations = eval_result.get("specializations", [])
        qualitative_assessment = eval_result.get("qualitative_assessment", "")
        confidence = eval_result.get("confidence", "low")
        caveats = eval_result.get("caveats", [])
    else:
        # LLM failed — fall back to hard findings only
        seniority_level = inspection.seniority_signal
        primary_languages = inspection.languages_deep
        specializations = []
        qualitative_assessment = "Assessment unavailable — LLM evaluator failed."
        confidence = "low"
        caveats = ["LLM evaluator did not run"]

    issued_at = datetime.now(timezone.utc).isoformat()

    credential_fields = {
        "credential_type": "SeniorDevCredential",
        "credential_id": credential_id,
        "developer_handle": developer_handle,
        "repo_corpus_root": record["repo_corpus_root"],
        "commit_count": record["commit_count"],
        "years_active": inspection.years_active,
        "hard_seniority_signal": inspection.seniority_signal,
        "seniority_level": seniority_level,
        "primary_languages": primary_languages,
        "specializations": specializations,
        "has_test_culture": inspection.has_test_culture,
        "qualitative_assessment": qualitative_assessment,
        "confidence": confidence,
        "caveats": caveats,
        "issued_at": issued_at,
    }

    credential_hash = hashlib.sha256(
        json.dumps(credential_fields, sort_keys=True).encode()
    ).hexdigest()

    tee_quote = await sign_result({
        "credential_hash": credential_hash,
        "repo_corpus_root": record["repo_corpus_root"],
    })

    credential = SeniorDevCredential(
        **credential_fields,
        credential_hash=credential_hash,
        tee_quote=tee_quote,
        tee_attested=True,
    ).model_dump()

    await db.update_dev_cred_evaluated(credential_id, credential, tee_quote)

    return credential


# ---------------------------------------------------------------------------
# GET /api/devcred/{credential_id}
# ---------------------------------------------------------------------------

@router.get("/{credential_id}")
async def get_dev_credential(credential_id: str) -> dict:
    """Return status and credential (if evaluated)."""
    record = await db.get_dev_cred(credential_id)
    if record is None:
        raise HTTPException(status_code=404, detail="credential_id not found")

    return {
        "credential_id": credential_id,
        "status": record["status"],
        "repo_corpus_root": record["repo_corpus_root"],
        "commit_count": record["commit_count"],
        "developer_handle": record["developer_handle"],
        "credential": record["credential"],
        "tee_quote": record["tee_quote"],
        "created_at": record["created_at"],
    }
