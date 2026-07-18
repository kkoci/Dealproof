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
import re

import httpx
from fastapi import HTTPException

from app.devcred.agents.git_evaluator import GitEvaluatorAgent
from app.devcred.agents.git_inspector import GitInspectorAgent
from app.devcred.git_hasher import extract_commit_metrics
from app.devcred.routes import _enrich_sample_with_details, _fallback_evaluation, _fetch_all_branch_commits

# Matches standard/Unicode whitespace (\s already covers space, tab, newline, NBSP U+00A0,
# and BOM U+FEFF in Python's re module) plus invisible zero-width/directional format
# characters \s does NOT cover — confirmed via direct trace against the real GitHub API
# (2026-07): a zero-width space or a non-breaking space anywhere in a "owner/repo" string
# reaches GitHub as a literal percent-encoded byte in the URL path and GitHub genuinely
# returns 404 for it — indistinguishable from "repo doesn't exist" in our own error
# message. None of these characters are ever legitimately part of a GitHub owner/repo
# identifier, so stripping them anywhere in the string (not just the edges, unlike
# str.strip()/JS .trim()) is always safe. Mirrors the identical character class used
# client-side in CandidateSession.jsx's VerifyCredentialPanel — same set on both sides, so
# a string that cleans one way in the browser cleans identically here for a caller that
# bypasses the frontend entirely (direct API call, a different client).
# Chars named explicitly by \uXXXX escape rather than pasted literally, so this source
# file's own bytes stay plain ASCII: U+200B zero-width space, U+200C zero-width
# non-joiner, U+200D zero-width joiner, U+200E left-to-right mark, U+200F right-to-left
# mark, U+2060 word joiner, U+FEFF byte-order mark, U+00AD soft hyphen.
_INVISIBLE_CHARS_RE = re.compile("[\\s​‌‍‎‏⁠﻿­]")


def clean_repo_name(raw: str) -> str:
    """Strips whitespace and invisible Unicode format characters from anywhere in `raw`."""
    return _INVISIBLE_CHARS_RE.sub("", raw)


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
