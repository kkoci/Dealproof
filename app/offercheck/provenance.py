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

Reuses app.devcred's full two-layer pipeline verbatim: the GitHub-fetch pipeline
(branch-iteration + SHA deduplication — see app.devcred.routes._fetch_all_branch_commits),
the deterministic GitInspectorAgent, AND the LLM GitEvaluatorAgent. The semantic layer
is Dev Credential's actual differentiator (qualitative assessment, specializations,
confidence-graded seniority beyond the raw deterministic signal) — an earlier version of
this module cut it to save one Claude call per verification. That cut was wrong: it
silently shipped a lesser credential instead of solving the cost/latency concern.
The concern is real and is instead solved the same way this vertical solves every other
Claude-call cost-drain risk — a tighter per-IP rate limit (see
app.offercheck.rate_limit.check_provenance_verify, 3/hour/IP, matching app.devcred's own
/evaluate limit exactly now that this endpoint also makes a paid Claude call, not just a
GitHub fetch) — not by removing the feature.

Same non-fatal discipline as app.devcred.routes.evaluate_credential: if GitEvaluatorAgent
fails (LLM error, malformed response), app.devcred.routes._fallback_evaluation produces a
minimal evaluation from the hard findings alone rather than failing the whole verification
— reused directly, not reimplemented, so both products degrade identically.
"""
import httpx
from fastapi import HTTPException

from app.devcred.agents.git_evaluator import GitEvaluatorAgent
from app.devcred.agents.git_inspector import GitInspectorAgent
from app.devcred.git_hasher import extract_commit_metrics
from app.devcred.routes import _enrich_sample_with_details, _fallback_evaluation, _fetch_all_branch_commits


async def verify_git_provenance(github_token: str, repos: list[str]) -> dict:
    """
    Fetches commits across every branch of each repo (deduplicated by SHA), computes
    deterministic metrics, runs GitInspectorAgent (hard findings), then GitEvaluatorAgent
    (qualitative assessment grounded in those hard findings — seniority_level can only
    move up from hard_seniority_signal, never down, enforced in code inside
    GitEvaluatorAgent itself). Returns a summary dict safe to store on a Session and
    expose via SessionView.candidate_provenance_credential — no repo names, no employer
    names, no raw token, matching app.devcred's own SeniorDevCredential privacy schema.

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
    hard = GitInspectorAgent().inspect(metrics)

    evaluation = await GitEvaluatorAgent().evaluate(metrics, hard)
    if evaluation is None:
        evaluation = _fallback_evaluation(hard, metrics)

    return {
        "hard_seniority_signal": hard.seniority_signal,
        "years_active": hard.years_active,
        "languages_deep": hard.languages_deep,
        "has_test_culture": hard.has_test_culture,
        "consistent_contribution": hard.consistent_contribution,
        "avg_commit_quality": hard.avg_commit_quality,
        "total_commits": metrics["total_commits"],
        "seniority_level": evaluation.seniority_level,
        "primary_languages": evaluation.primary_languages,
        "specializations": evaluation.specializations,
        "qualitative_assessment": evaluation.qualitative_assessment,
        "confidence": evaluation.confidence,
        "caveats": evaluation.caveats,
    }
