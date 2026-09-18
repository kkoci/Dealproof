"""
Developer credential routes — /api/devcred/.

Phase 1: POST /api/devcred/ingest — fetch commits, extract metrics, compute corpus root.
Phase 3: POST /api/devcred/{credential_id}/evaluate — full pipeline → SeniorDevCredential + TDX quote.
         GET  /api/devcred/{credential_id}           — status + credential if complete.

Revoked-repo-access fallback (three routes, by design):

  A candidate's GitHub token can outlive their access to a repo they actually worked
  in — e.g. they left the employer that owned it. Before this addition, that produced
  a plain 404 from _fetch_all_branch_commits/_fetch_commit_list with no distinction
  between "recently revoked, a fallback exists" and "genuinely nothing we can do." Three
  routes now exist, tried roughly in this order as access recency decreases:

    Route A — direct_access  (unchanged): POST /ingest fetches commits live via the
      GitHub API, exactly as before. Untouched beyond the minimal branching described
      below needed to detect a 404 and fall through to Route B.

    Route B — events_stream: when every requested repo 404s, ingest_repos() falls back
      to GitHub's events timeline (GET /users/{username}/events) for the token owner —
      this endpoint needs no access to the specific repo, only that the account itself
      is queried directly, and it returns event types (PushEvent, PullRequestEvent,
      PullRequestReviewEvent, ...) without ever exposing source code. Confirmed against
      GitHub's current REST API docs (2026-09, not assumed from an earlier design pass):
      the timeline holds up to 300 events, and only events from the past 30 days are
      included — narrower than the ~90-day figure an earlier design conversation
      assumed. inspect_events() (app/devcred/agents/git_inspector.py) is structurally
      capped below "senior" — there's no diff/language/test-culture signal in an event
      stream to justify that grade, so evaluate_credential() skips the paid
      GitEvaluatorAgent call entirely for this route (nothing for an LLM to usefully add
      over the deterministic event counts) — no extra Claude cost, so this stays inside
      the same 10/hour /ingest + /{id}/evaluate rate-limit envelope as Route A, not a
      new bucket.

    Route C — local_git_upload: POST /ingest-local. For access revoked longer ago than
      the events window — the actual target case, someone proving employment from years
      back — the candidate uploads derived metrics from a local .git folder they still
      hold (frontend: File System Access API, see frontend/src/pages/devcred/
      LocalGitUpload.jsx), cryptographically bound to a key via a fresh signature (see
      app/devcred/local_signature.py for the full signing contract and the client/server
      verification split). Only aggregate metrics ever reach this endpoint — no file
      paths (commits omit `files` entirely, so languages/test-culture are structurally
      empty here too, same discipline as Route B) and no raw diffs. The signature IS
      verified server-side (local_signature.verify_signature) — trusting an unverified
      client claim of "I validated this myself" would make this indistinguishable from
      Route D in every way except formatting.

  Route D — self_reported (POST /self-report): the honest dead end. If a repo is
    private, revoked outside the events window, and never cloned locally, there is
    genuinely nothing to verify. This path never fabricates a score — it records
    plain contextual claims (role title, company name, dates) with verified=False and
    provenance_method=self_reported, and that distinction is unambiguous everywhere
    this credential is read (see schemas.SeniorDevCredential's own docstring).

Privacy constraints:
  - github_token: used in-memory during this request, never written to disk or DB
  - repo names: hashed into corpus_root only, never stored in DB
  - employer names: never appear in the system for a verified credential — the one
    deliberate exception is Route D's self_reported context, which exists precisely
    to hold an honest, explicitly-unverified employer claim (see schemas.py)
  - raw diffs + file paths: not stored, only aggregate metrics (Routes A/B/C alike)

SECURITY: Any endpoint that calls an external paid API (Claude, GitHub)
must be rate-limited. This is a standing requirement.
"""
import hashlib
import json
import math
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import app.db as db
from app.devcred.git_hasher import (
    compute_repo_corpus_root,
    compute_events_corpus_root,
    deduplicate_commits,
    extract_commit_metrics,
    extract_event_metrics,
)
from app.devcred.agents.git_inspector import GitInspectorAgent, GitInspectionReport, inspect_events
from app.devcred.agents.git_evaluator import GitEvaluatorAgent, GitEvaluation
from app.devcred.local_signature import canonical_payload, verify_signature
from app.devcred.schemas import (
    SeniorDevCredential,
    DevCredEvaluateResponse,
    DevCredStatusResponse,
    LocalGitUploadRequest,
    LocalGitUploadResponse,
    SelfReportedRequest,
)
from app.rate_limit import limiter
from app.tee.attestation import sign_result

router = APIRouter(prefix="/api/devcred", tags=["devcred"])

GITHUB_API = "https://api.github.com"
MAX_COMMITS_PER_REPO = 300
DETAIL_SAMPLE_SIZE = 50  # commits fetched individually for file/diff details
DAILY_EVAL_LIMIT = 50  # hard stop across all users/IPs, resets at UTC midnight

# Route B — confirmed against GitHub's current REST API docs (2026-09):
# https://docs.github.com/en/rest/activity/events lists a hard 300-event cap and a
# 30-day retention window for GET /users/{username}/events. Kept as named constants
# (not hardcoded inline) so a future GitHub change only needs updating here.
GITHUB_EVENTS_MAX_EVENTS = 300
GITHUB_EVENTS_PER_PAGE = 100


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
    provenance_method: str = "direct_access"  # "direct_access" | "events_stream" — see module docstring
    event_count: int | None = None            # populated only when provenance_method == "events_stream"


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


async def _fetch_branches(token: str, repo: str, client: httpx.AsyncClient) -> list[dict]:
    """
    Paginate the repo's full branch list. Returns [{"name": str, "sha": str}, ...] — the
    tip commit SHA per branch is included in the same response GitHub already gives us for
    the branch listing, so this needs no extra per-branch call to learn it.
    """
    headers = _github_headers(token)
    branches: list[dict] = []
    page = 1

    while True:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/branches",
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=30.0,
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Repo not found or token lacks access: {repo}")
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="GitHub token invalid or expired")
        if resp.status_code == 403:
            raise HTTPException(
                status_code=429,
                detail=f"GitHub API rate limit hit while listing branches for {repo} — try again shortly",
            )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub API error {resp.status_code} while listing branches for {repo}",
            )

        page_data = resp.json()
        if not page_data:
            break
        for b in page_data:
            branches.append({"name": b["name"], "sha": (b.get("commit") or {}).get("sha")})
        if len(page_data) < 100:
            break
        page += 1

    return branches


async def _fetch_commit_list(token: str, repo: str, client: httpx.AsyncClient, ref: str | None = None) -> list[dict]:
    """
    Paginate up to MAX_COMMITS_PER_REPO commits from the GitHub commits list endpoint,
    starting from `ref` (a branch name) if given — otherwise GitHub defaults to the repo's
    default branch, same as before this parameter existed.
    Returns lightweight commit dicts: sha, author, timestamp, message, is_merge.
    """
    headers = _github_headers(token)
    commits: list[dict] = []
    page = 1
    params_base: dict = {"per_page": 100}
    if ref:
        params_base["sha"] = ref

    while len(commits) < MAX_COMMITS_PER_REPO:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/commits",
            headers=headers,
            params={**params_base, "page": page},
            timeout=30.0,
        )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Repo not found or token lacks access: {repo}",
            )
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="GitHub token invalid or expired")
        if resp.status_code == 403:
            raise HTTPException(
                status_code=429,
                detail=f"GitHub API rate limit hit while fetching {repo} — try again shortly",
            )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub API error {resp.status_code} while fetching {repo}",
            )

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


async def _fetch_all_branch_commits(token: str, repo: str, client: httpx.AsyncClient) -> list[dict]:
    """
    Fetches commits reachable from every branch in the repo, not just the default branch —
    a commit that only ever landed on a feature/PR branch (never merged) was previously
    invisible to this pipeline entirely. Deduplicates by SHA via git_hasher.deduplicate_commits
    so a commit already merged into an earlier-processed branch is only counted once.

    Short-circuits branches whose tip commit is already in the accumulated set — by git's DAG
    structure, that branch's entire history is therefore already covered, so its commit list
    never needs to be paginated at all. Stops once MAX_COMMITS_PER_REPO unique commits have
    been collected, same cap as the single-branch path had.
    """
    branches = await _fetch_branches(token, repo, client)
    seen_shas: set[str] = set()
    all_commits: list[dict] = []

    for branch in branches:
        if len(all_commits) >= MAX_COMMITS_PER_REPO:
            break
        tip_sha = branch.get("sha")
        if tip_sha and tip_sha in seen_shas:
            continue  # this branch's whole history is already covered by an earlier branch

        branch_commits = await _fetch_commit_list(token, repo, client, ref=branch["name"])
        new_commits = deduplicate_commits(branch_commits, seen_shas)
        all_commits.extend(new_commits)
        seen_shas.update(c["sha"] for c in new_commits)

    return all_commits[:MAX_COMMITS_PER_REPO]


async def _fetch_user_events(token: str, username: str, client: httpx.AsyncClient) -> list[dict]:
    """
    Route B — fetches the token owner's events timeline (GET /users/{username}/events).
    Passing the token authenticates the request as that same account, which per GitHub's
    docs surfaces that account's private events too, not just public ones — needed here
    since a revoked-access repo's activity would otherwise never appear at all.

    Paginates up to GITHUB_EVENTS_MAX_EVENTS (300) — GitHub's own hard cap, confirmed
    against current docs (see module docstring). No repo-specific access is required:
    this is the entire reason this endpoint is usable as a fallback when repo access
    itself has been revoked.
    """
    headers = _github_headers(token)
    events: list[dict] = []
    page = 1

    while len(events) < GITHUB_EVENTS_MAX_EVENTS:
        resp = await client.get(
            f"{GITHUB_API}/users/{username}/events",
            headers=headers,
            params={"per_page": GITHUB_EVENTS_PER_PAGE, "page": page},
            timeout=30.0,
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"GitHub user not found: {username}")
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="GitHub token invalid or expired")
        if resp.status_code == 403:
            raise HTTPException(
                status_code=429,
                detail=f"GitHub API rate limit hit while fetching events for {username} — try again shortly",
            )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub API error {resp.status_code} while fetching events for {username}",
            )

        page_data = resp.json()
        if not page_data:
            break
        events.extend(page_data)
        if len(page_data) < GITHUB_EVENTS_PER_PAGE:
            break
        page += 1

    return events[:GITHUB_EVENTS_MAX_EVENTS]


def _events_referencing_repos(events: list[dict], repos: list[str]) -> list[dict]:
    """Filters events down to those whose repo.name matches one of the given owner/repo strings."""
    wanted = {r.lower() for r in repos}
    return [e for e in events if ((e.get("repo") or {}).get("name") or "").lower() in wanted]


def _dead_end_detail(revoked_repos: list[str]) -> dict:
    """
    Structured 404 detail for when neither Route A nor Route B produced anything —
    lets the frontend distinguish "genuinely nothing we can do via GitHub" (offer
    Route C / Route D) from an ordinary error, rather than showing a dead-end message
    with no path forward.
    """
    return {
        "error": "repo_access_revoked_no_recent_activity",
        "message": (
            "No accessible commits and no matching recent GitHub activity were found for: "
            f"{', '.join(revoked_repos)}. If you still have a local copy of the repository, "
            "you can upload derived metrics with a cryptographic signature instead. "
            "Otherwise you can submit unverified employment details."
        ),
        "revoked_repos": revoked_repos,
        "fallback_available": ["local_git_upload", "self_reported"],
    }


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
@limiter.limit("10/hour")
async def ingest_repos(request: Request, body: DevCredIngest) -> DevCredIngestResponse:
    """
    Fetch commits from GitHub, extract deterministic metrics, compute corpus root.
    GitHub token is used in-memory only — never written to disk or database.

    Rate-limited to 10 requests/hour/IP — GitHub API is free tier but still
    an external call; see module docstring SECURITY note.
    """
    for repo in body.repos:
        if "/" not in repo or repo.startswith("/") or repo.endswith("/"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid repo format (expected owner/repo): {repo}",
            )

    all_commits: list[dict] = []
    revoked_repos: list[str] = []
    developer_handle = "unknown"

    async with httpx.AsyncClient() as client:
        developer_handle = await _fetch_github_username(body.github_token, client)

        for repo in body.repos:
            # Minimal branching for Route B: a 404 here means "no access to THIS repo"
            # (revoked, renamed, or never granted) — not "the request as a whole must
            # fail." Any other status still raises exactly as before (401 invalid
            # token, 429 rate limit, 502 upstream error all remain hard failures — a
            # dead token or a rate limit isn't "revoked access to one repo", it's a
            # reason Route B would fail too, so there's no point trying it).
            try:
                commits = await _fetch_all_branch_commits(body.github_token, repo, client)
                commits = await _enrich_sample_with_details(body.github_token, repo, commits, client)
                all_commits.extend(commits)
            except HTTPException as exc:
                if exc.status_code == 404:
                    revoked_repos.append(repo)
                    continue
                raise

        if all_commits:
            # Route A succeeded for at least one repo — unchanged behavior below.
            pass
        elif revoked_repos:
            # Every requested repo is inaccessible. Attempt Route B before giving up:
            # the account's own events timeline needs no repo-specific access at all.
            events = await _fetch_user_events(body.github_token, developer_handle, client)
            matching_events = _events_referencing_repos(events, revoked_repos)

            if not matching_events:
                raise HTTPException(status_code=404, detail=_dead_end_detail(revoked_repos))

            event_metrics = extract_event_metrics(matching_events)
            events_corpus_root = compute_events_corpus_root(matching_events)

            await db.create_dev_credential(
                credential_id=body.credential_id,
                developer_handle=developer_handle,
                repo_corpus_root=events_corpus_root,
                commit_count=0,
                metrics=event_metrics,
                provenance_method="events_stream",
                event_count=event_metrics["total_events"],
            )

            return DevCredIngestResponse(
                credential_id=body.credential_id,
                corpus_root=events_corpus_root,
                commit_count=0,
                repo_count=len(body.repos),
                metrics_preview={
                    "total_events": event_metrics["total_events"],
                    "active_months": event_metrics["active_months"],
                    "event_type_counts": event_metrics["event_type_counts"],
                    "first_event_date": event_metrics["first_event_date"],
                    "last_event_date": event_metrics["last_event_date"],
                },
                provenance_method="events_stream",
                event_count=event_metrics["total_events"],
            )

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


def _events_evaluation(hard) -> GitEvaluation:
    """
    Route B's evaluation step — deliberately never calls GitEvaluatorAgent (see module
    docstring: there's no diff/language/test-culture signal in an event stream for an
    LLM to meaningfully add beyond restating the deterministic event counts, so this
    route makes no Claude call at all).
    """
    top_types = sorted(hard.event_type_counts.items(), key=lambda kv: -kv[1])[:3]
    pattern = ", ".join(f"{count}x {etype}" for etype, count in top_types) or "no events"
    return GitEvaluation(
        seniority_level=hard.seniority_signal,
        primary_languages=[],
        specializations=[],
        contribution_pattern=f"GitHub activity timeline: {pattern} over {hard.active_months} active month(s).",
        qualitative_assessment=(
            "Derived from GitHub's public/private activity timeline only, not direct repository "
            "access — no diffs, languages, or test culture were visible for this assessment."
        ),
        confidence="low" if hard.total_events < 100 else "medium",
        caveats=[
            "Verified via GitHub events timeline fallback, not direct repository access",
            "No language, diff, or test-culture signal was available for this route",
            "Seniority signal is structurally capped below 'senior' for this route",
        ],
    )


# ---------------------------------------------------------------------------
# Phase 3 endpoints
# ---------------------------------------------------------------------------

@router.post("/{credential_id}/evaluate", response_model=DevCredEvaluateResponse)
@limiter.limit("3/hour")
async def evaluate_credential(request: Request, credential_id: str) -> DevCredEvaluateResponse:
    """
    Run the full two-layer analysis pipeline on an ingested corpus.

    Pipeline:
      1. GitInspectorAgent.inspect(metrics) → hard findings (deterministic)
      2. GitEvaluatorAgent.evaluate(metrics, hard_findings) → qualitative fields
      3. Build SeniorDevCredential
      4. credential_hash = SHA-256(credential fields)
      5. Embed {credential_hash, repo_corpus_root} in TDX report_data
      6. Persist to dev_credentials, return credential + TDX quote

    Rate-limited to 3 requests/hour/IP, plus a hard stop of DAILY_EVAL_LIMIT
    calls/day across all callers — this endpoint makes a paid Claude call;
    see module docstring SECURITY note.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    daily_count = await db.increment_daily_eval_count(today)
    if daily_count > DAILY_EVAL_LIMIT:
        await db.decrement_daily_eval_count(today)
        raise HTTPException(
            status_code=503,
            detail=f"Daily evaluation limit reached ({DAILY_EVAL_LIMIT}/day across all users) — try again tomorrow.",
        )

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
    provenance_method: str = record.get("provenance_method") or "direct_access"

    issued_at = datetime.now(timezone.utc).isoformat()

    if provenance_method == "events_stream":
        # Route B: deterministic-only, no LLM call (see _events_evaluation docstring)
        hard = inspect_events(metrics)
        evaluation = _events_evaluation(hard)
        cred_fields = {
            "credential_type": "SeniorDevCredential",
            "credential_id": credential_id,
            "developer_handle": developer_handle,
            "provenance_method": provenance_method,
            "verified": True,
            "repo_corpus_root": repo_corpus_root,
            "commit_count": 0,
            "event_count": record.get("event_count"),
            "years_active": 0.0,
            "hard_seniority_signal": hard.seniority_signal,
            "seniority_level": evaluation.seniority_level,
            "primary_languages": evaluation.primary_languages,
            "specializations": evaluation.specializations,
            "has_test_culture": False,
            "qualitative_assessment": evaluation.qualitative_assessment,
            "confidence": evaluation.confidence,
            "caveats": evaluation.caveats,
            "issued_at": issued_at,
        }
    else:
        # Route A (direct_access) and Route C (local_git_upload) share this pipeline —
        # local_git_upload's metrics dict has the same shape (files omitted, so
        # languages/test_file_ratio are structurally empty, but GitInspectorAgent and
        # GitEvaluatorAgent otherwise run unmodified).
        inspector = GitInspectorAgent()
        hard = inspector.inspect(metrics)

        evaluator = GitEvaluatorAgent()
        evaluation = await evaluator.evaluate(metrics, hard)
        if evaluation is None:
            evaluation = _fallback_evaluation(hard, metrics)

        caveats = list(evaluation.caveats)
        if provenance_method == "local_git_upload":
            caveats.append(
                "Verified via a signed local .git upload, not live GitHub repository access — "
                "no file paths were available, so language and test-culture signal is absent"
            )

        cred_fields = {
            "credential_type": "SeniorDevCredential",
            "credential_id": credential_id,
            "developer_handle": developer_handle,
            "provenance_method": provenance_method,
            "verified": True,
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
            "caveats": caveats,
            "issued_at": issued_at,
        }

    # Step 4 — credential_hash over all fields (before tee_attested is set)
    credential_hash = _hash_credential(cred_fields)
    cred_fields["credential_hash"] = credential_hash

    # Step 5 — TDX attestation: bind credential_hash + corpus_root (non-fatal,
    # same resilience pattern as the main deal re-attestation in api/routes.py)
    tee_quote: str | None = None
    try:
        tee_quote = await sign_result({
            "credential_hash": credential_hash,
            "repo_corpus_root": repo_corpus_root,
        })
    except Exception:
        pass
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


# ---------------------------------------------------------------------------
# Route C — local_git_upload
# ---------------------------------------------------------------------------

@router.post("/ingest-local", response_model=LocalGitUploadResponse)
@limiter.limit("10/hour")
async def ingest_local_git(request: Request, body: LocalGitUploadRequest) -> LocalGitUploadResponse:
    """
    Route C ingest — accepts already-derived metrics from a local .git folder the
    candidate still holds, cryptographically bound to a key via a fresh signature
    over canonical_payload(credential_id, developer_handle, corpus_root). See
    app/devcred/local_signature.py for the full signing contract and why the
    cryptographic verification happens here, server-side, rather than being trusted
    from an unverified client claim.

    No GitHub API call and no Claude call happen in this endpoint — corpus_root is
    recomputed server-side from the submitted commits (never trusted from the
    client), which is also what the signature is verified against. Still
    rate-limited at the same 10/hour tier as /ingest: this does real verification
    work per call and is the natural target for a script hammering it with garbage
    signatures, even though nothing here is a paid external call.

    On success, persists as status='ingested' with provenance_method='local_git_upload'
    — the SAME POST /{credential_id}/evaluate endpoint used by Route A then completes
    the credential (see evaluate_credential's local_git_upload branch), including a
    real GitEvaluatorAgent call, since commit messages/diff sizes (unlike Route B's
    bare event counts) still carry real qualitative signal even with file paths absent.
    """
    if not body.commits:
        raise HTTPException(status_code=400, detail="At least one commit is required")

    commit_dicts = [c.model_dump() for c in body.commits]
    corpus_root = compute_repo_corpus_root(commit_dicts)

    payload = canonical_payload(body.credential_id, body.developer_handle, corpus_root)
    result = verify_signature(payload, body.signature, body.public_key, body.signature_format)
    if not result.valid:
        raise HTTPException(status_code=401, detail=f"Signature verification failed: {result.error}")

    # Best-effort identity cross-check: does GitHub currently list this SSH key
    # against the claimed account? Non-fatal and never required to pass — a
    # candidate proving years-old employment may well have rotated keys since,
    # which is exactly the case this whole route exists to still support.
    github_key_currently_listed: bool | None = None
    if body.signature_format == "ssh":
        try:
            key_material = body.public_key.strip().split()[1]
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GITHUB_API}/users/{body.developer_handle}/keys", timeout=10.0
                )
                if resp.status_code == 200:
                    github_key_currently_listed = any(
                        key_material in (k.get("key") or "") for k in resp.json()
                    )
        except Exception:
            github_key_currently_listed = None

    # files=[] and is_merge=False: no file paths ever reach this endpoint, and merge
    # detection isn't available from the envelope shape this route accepts — both
    # disclosed via evaluate_credential's local_git_upload caveat, not silently absent.
    metrics_input = [{**c, "is_merge": False, "files": []} for c in commit_dicts]
    metrics = extract_commit_metrics(metrics_input)

    await db.create_dev_credential(
        credential_id=body.credential_id,
        developer_handle=body.developer_handle,
        repo_corpus_root=corpus_root,
        commit_count=len(commit_dicts),
        metrics=metrics,
        provenance_method="local_git_upload",
    )

    return LocalGitUploadResponse(
        credential_id=body.credential_id,
        corpus_root=corpus_root,
        commit_count=len(commit_dicts),
        key_fingerprint=result.key_fingerprint,
        github_key_currently_listed=github_key_currently_listed,
    )


# ---------------------------------------------------------------------------
# Route D — self_reported (the honest dead end)
# ---------------------------------------------------------------------------

@router.post("/self-report", response_model=DevCredEvaluateResponse)
@limiter.limit("10/hour")
async def self_report_credential(request: Request, body: SelfReportedRequest) -> DevCredEvaluateResponse:
    """
    Route D — no verifiable git signal exists (repo private, revocation older than
    GitHub's events window, no local .git copy). Records the candidate's own claim
    as plain context, never as a graded/scored credential: seniority_level is left
    at its schema default and is not a real assessment (see qualitative_assessment
    below, and schemas.SeniorDevCredential.verified, which is False here). No
    GitHub or Claude call happens in this endpoint — there's nothing to fetch or
    evaluate — so it goes straight to a complete record, unlike the ingest→evaluate
    split the other three routes use.
    """
    existing = await db.get_dev_credential(body.credential_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Credential already exists: {body.credential_id}")

    issued_at = datetime.now(timezone.utc).isoformat()
    placeholder_root = f"self-reported:{body.credential_id}"  # never a real hash — see db.py docstring
    developer_handle = body.developer_handle or "unknown"

    cred_fields = {
        "credential_type": "SeniorDevCredential",
        "credential_id": body.credential_id,
        "developer_handle": developer_handle,
        "provenance_method": "self_reported",
        "verified": False,
        "repo_corpus_root": None,
        "commit_count": 0,
        "years_active": 0.0,
        "hard_seniority_signal": None,
        "seniority_level": "junior",
        "primary_languages": [],
        "specializations": [],
        "has_test_culture": False,
        "qualitative_assessment": (
            "No verifiable git signal is available for this entry. This record reflects the "
            "candidate's own unverified claim of employment, provided as context only."
        ),
        "confidence": "low",
        "caveats": [
            "UNVERIFIED — self-reported only; no cryptographic or platform evidence backs this entry",
        ],
        "self_reported": {
            "role_title": body.role_title,
            "company_name": body.company_name,
            "employment_start": body.employment_start,
            "employment_end": body.employment_end,
        },
        "issued_at": issued_at,
    }

    credential_hash = _hash_credential(cred_fields)
    cred_fields["credential_hash"] = credential_hash

    # Attests that THIS RECORD — exactly as labeled unverified — was processed inside
    # the TEE. It does NOT mean the underlying employment claim was verified; see
    # SeniorDevCredential.tee_attested's docstring.
    tee_quote: str | None = None
    try:
        tee_quote = await sign_result({
            "credential_hash": credential_hash,
            "repo_corpus_root": placeholder_root,
        })
    except Exception:
        pass
    tee_attested = bool(tee_quote)
    cred_fields["tee_attested"] = tee_attested

    credential = SeniorDevCredential(**cred_fields)

    await db.create_dev_credential_complete(
        credential_id=body.credential_id,
        developer_handle=developer_handle,
        repo_corpus_root=placeholder_root,
        credential=cred_fields,
        tee_quote=tee_quote,
        provenance_method="self_reported",
    )

    return DevCredEvaluateResponse(
        credential_id=body.credential_id,
        credential=credential,
        tee_quote=tee_quote,
        tee_attested=tee_attested,
    )
