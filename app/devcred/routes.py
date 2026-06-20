"""
Developer credential routes — /api/devcred/.

Phase 1: Git ingestion + corpus hashing.
  POST /api/devcred/ingest — fetch commits, extract metrics, compute corpus root.

Privacy constraints:
  - github_token: used in-memory during this request, never written to disk or DB
  - repo names: hashed into corpus_root only, never stored in DB
  - employer names: never appear in the system
  - raw diffs + file paths: not stored, only aggregate metrics
"""
import math
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import app.db as db
from app.devcred.git_hasher import compute_repo_corpus_root, extract_commit_metrics

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
