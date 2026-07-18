"""
Provenance-credential verification for Offer Check — lets a candidate optionally
prove real-world engineering experience via their git commit history, giving the
employer a trust signal alongside the negotiation itself. Added as a pre-negotiation
step at the employer's option (see EmployerInviteRequest.require_provenance_credential
and negotiation.apply_move()'s gate).

Framed deliberately as "the first evidence type of a general provenance-verification
primitive," per the merge design that introduced this module — but no abstraction for
a second evidence type is built here; that would be speculative generality with
nothing yet to generalize over. Extending this to other evidence types (a diploma, a
portfolio, a credential from another platform) is future work, flagged, not designed.
This module, and the Session fields / SessionView fields / apply_move() gate around
it, are named generically (`provenance`, not `git`) specifically so that future work
doesn't require a rename — but the implementation below is 100% git/GitHub-specific.

Reuses app.devcred's GitHub-fetch pipeline verbatim (branch-iteration + SHA
deduplication — see app.devcred.routes._fetch_all_branch_commits) and its
deterministic GitInspectorAgent. Deliberately does NOT reuse app.devcred's LLM
GitEvaluatorAgent: Offer Check's provenance check is a supporting signal for the
negotiation flow, not devcred's own first-class credential product, so the extra
latency/cost/complexity of a second Claude call per verification isn't justified
here. This is a scope reduction from "reuse devcred's ingest/evaluate logic" in the
literal sense — the ingest half is reused verbatim; the evaluate half is replaced
with the cheaper deterministic-only layer.
"""
import httpx
from fastapi import HTTPException

from app.devcred.agents.git_inspector import GitInspectorAgent
from app.devcred.git_hasher import extract_commit_metrics
from app.devcred.routes import _enrich_sample_with_details, _fetch_all_branch_commits


async def verify_git_provenance(github_token: str, repos: list[str]) -> dict:
    """
    Fetches commits across every branch of each repo (deduplicated by SHA),
    computes deterministic metrics, and runs GitInspectorAgent. Returns a summary
    dict safe to store on a Session and expose via SessionView.candidate_provenance_credential
    — no repo names, no employer names, no raw token, matching app.devcred's own
    SeniorDevCredential privacy schema.

    GitHub fetch failures (bad token, repo not found, rate limit) propagate as the
    same HTTPException app.devcred.routes already raises for them — reused, not
    re-wrapped, so the caller gets the same accurate status code/detail either way.
    """
    all_commits: list[dict] = []
    async with httpx.AsyncClient() as client:
        for repo in repos:
            commits = await _fetch_all_branch_commits(github_token, repo, client)
            commits = await _enrich_sample_with_details(github_token, repo, commits, client)
            all_commits.extend(commits)

    if not all_commits:
        raise HTTPException(status_code=422, detail="No commits found across specified repos")

    metrics = extract_commit_metrics(all_commits)
    report = GitInspectorAgent().inspect(metrics)

    return {
        "seniority_signal": report.seniority_signal,
        "years_active": report.years_active,
        "languages_deep": report.languages_deep,
        "has_test_culture": report.has_test_culture,
        "consistent_contribution": report.consistent_contribution,
        "avg_commit_quality": report.avg_commit_quality,
        "total_commits": metrics["total_commits"],
    }
