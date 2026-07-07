"""
πCreds-style conduct credential — Phase 3 (see build_spec_offer_check.md).

"Offer verified, negotiation conducted fairly" — deterministic checks over a
closed session's round history, mirroring app/picreds/constraints.py's core
principle: hard invariants are computed in code, never left to an LLM to
assert. There is no LLM call in this module at all.

Privacy: the checks below read RoundEntry.value (the raw counter amounts,
stored internally in app.offercheck.store) to compute capitulation and
convergence, but the returned OfferVerifiedCredential never contains a raw
dollar figure — only booleans, counts, and a qualitative summary. Same
boundary as everywhere else in this vertical: raw numbers stay server-side.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.offercheck.store import Session

CAPITULATION_THRESHOLD = 0.40


@dataclass
class OfferVerifiedCredential:
    session_id: str
    genuine_negotiation: bool
    round_count: int
    outcome: str  # "agreed" | "walkaway" | "expired"
    issues: list[str]
    summary: str
    credential_hash: str


_OUTCOME_BY_STATE = {"AGREED": "agreed", "WALKAWAY": "walkaway", "EXPIRED": "expired"}


def _capitulation_issues(values_in_order: list[float], actor: str) -> list[str]:
    issues = []
    for prev, curr in zip(values_in_order, values_in_order[1:]):
        if prev == 0:
            continue
        pct_change = abs(curr - prev) / abs(prev)
        if pct_change > CAPITULATION_THRESHOLD:
            issues.append(f"{actor} moved {pct_change:.0%} in a single round (> {CAPITULATION_THRESHOLD:.0%} threshold)")
    return issues


def _convergence_issues(candidate_values: list[float], employer_values: list[float]) -> list[str]:
    issues = []
    for prev, curr in zip(candidate_values, candidate_values[1:]):
        if curr > prev:
            issues.append("candidate's ask increased between rounds (expected non-increasing)")
            break
    for prev, curr in zip(employer_values, employer_values[1:]):
        if curr < prev:
            issues.append("employer's offer decreased between rounds (expected non-decreasing)")
            break
    return issues


def compute_credential(session: "Session") -> OfferVerifiedCredential:
    if session.state not in ("AGREED", "WALKAWAY", "EXPIRED"):
        raise ValueError(f"cannot compute a credential for a non-terminal session (state={session.state})")

    candidate_values = [session.original_candidate_ask] + [
        r.value for r in session.history if r.actor == "candidate" and r.move == "counter" and r.value is not None
    ]
    employer_values = [
        r.value for r in session.history if r.actor == "employer" and r.move == "counter" and r.value is not None
    ]

    issues = (
        _capitulation_issues(candidate_values, "candidate")
        + _capitulation_issues(employer_values, "employer")
        + _convergence_issues(candidate_values, employer_values)
    )

    genuine_negotiation = len(issues) == 0
    outcome = _OUTCOME_BY_STATE[session.state]
    round_count = session.round_number

    if genuine_negotiation:
        summary = f"{round_count}-round negotiation, {outcome}, no conduct issues detected."
    else:
        summary = f"{round_count}-round negotiation, {outcome}, issues detected: {'; '.join(issues)}"

    credential = OfferVerifiedCredential(
        session_id=session.id,
        genuine_negotiation=genuine_negotiation,
        round_count=round_count,
        outcome=outcome,
        issues=issues,
        summary=summary,
        credential_hash="",
    )
    credential.credential_hash = _hash_credential(credential)
    return credential


def _hash_credential(credential: OfferVerifiedCredential) -> str:
    payload = {
        "session_id": credential.session_id,
        "genuine_negotiation": credential.genuine_negotiation,
        "round_count": credential.round_count,
        "outcome": credential.outcome,
        "issues": sorted(credential.issues),
        "summary": credential.summary,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
