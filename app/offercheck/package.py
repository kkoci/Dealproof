"""
Full compensation package negotiation — Phase 2B (offercheck_phase2_spec.md).

Phase 2A negotiates a single number (base salary) through the reused human
state machine (app.offercheck.negotiation.apply_move). A package can't flow
through that machine — RoundEntry.value and every gap/credential calculation
built on it are scalar. Rather than retrofit the Phase 1 human flow to carry
arbitrary structured values, package negotiation is agentic-only and lives in
a parallel, package-shaped mirror of the same state machine (see
app.offercheck.agents.package_mediator and the package_* fields on Session)
— same turn-alternation, same max-5-rounds-then-expire, same "sealed inputs
never cross, only the round's package + move do" contract as Phase 2A.

Package terms exchanged each round:
  base, equity_grant, vesting_years, cliff_months, signing_bonus,
  annual_bonus_pct, remote, start_date_days, pto_days
"""
import hashlib
import json
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.offercheck.store import Session

RemotePolicy = Literal["remote", "hybrid", "onsite"]

PACKAGE_FIELDS = (
    "base", "equity_grant", "vesting_years", "cliff_months", "signing_bonus",
    "annual_bonus_pct", "remote", "start_date_days", "pto_days",
)

CONVERGENCE_THRESHOLD = 0.02  # total comp within 2% => agents should lean toward accepting


def total_comp_value(package: dict) -> float:
    """
    Deterministic total-comp approximation used for convergence detection and
    for clamping packages to a floor/budget. This is NOT a real compensation
    model — it's a single number both agents can reason about consistently:

        total = base
              + annual_bonus_pct/100 * base    (recurring annual bonus)
              + equity_grant / vesting_years   (equity, annualized over vesting)
              + signing_bonus                  (one-time, counted at face value)

    PTO days, remote policy, start date, and cliff length are negotiated but
    don't move this number — they're not compensation in the same sense.
    """
    base = float(package.get("base", 0) or 0)
    bonus_pct = float(package.get("annual_bonus_pct", 0) or 0)
    equity = float(package.get("equity_grant", 0) or 0)
    vesting_years = float(package.get("vesting_years", 0) or 0) or 1.0
    signing = float(package.get("signing_bonus", 0) or 0)
    return base + (bonus_pct / 100) * base + equity / vesting_years + signing


def is_converged(candidate_total: float, employer_total: float, threshold: float = CONVERGENCE_THRESHOLD) -> bool:
    if employer_total <= 0:
        return False
    return abs(candidate_total - employer_total) / employer_total <= threshold


def clamp_candidate_package(package: dict, base_floor: float, total_comp_floor: float) -> dict:
    """
    Hard floors enforced in code, not just requested via the prompt — same
    discipline as CandidateAgent.floor in Phase 2A. If total comp still falls
    short after the base floor is applied, the shortfall is added to
    signing_bonus (the one term that doesn't distort the recurring package)
    rather than silently letting the package under-floor.
    """
    package = dict(package)
    if float(package.get("base", 0) or 0) < base_floor:
        package["base"] = base_floor
    shortfall = total_comp_floor - total_comp_value(package)
    if shortfall > 0:
        package["signing_bonus"] = float(package.get("signing_bonus", 0) or 0) + shortfall
    return package


def clamp_employer_package(package: dict, base_min: float, base_max: float, total_comp_budget: float) -> dict:
    """
    Hard ceiling enforced in code. Base is clamped into [base_min, base_max]
    first (base_max already reflects min(band_max, employer_authority_limit)
    — see package_mediator.build_package_agents). If total comp still exceeds
    budget, signing_bonus is trimmed first (most flexible term) — this is a
    best-effort trim, not a guarantee the result lands exactly at budget if
    base+equity alone exceed it; documented as a known limitation, not a bug.
    """
    package = dict(package)
    base = float(package.get("base", base_min) or base_min)
    package["base"] = max(base_min, min(base_max, base))
    overage = total_comp_value(package) - total_comp_budget
    if overage > 0:
        package["signing_bonus"] = max(0.0, float(package.get("signing_bonus", 0) or 0) - overage)
    return package


def normalize_package(raw: dict, fallback: dict) -> dict:
    """Fills any missing/invalid fields from `fallback` (the agent's last known package)."""
    package = {}
    for field in PACKAGE_FIELDS:
        value = raw.get(field) if isinstance(raw, dict) else None
        if value is None:
            value = fallback.get(field)
        package[field] = value
    if package.get("remote") not in ("remote", "hybrid", "onsite"):
        package["remote"] = fallback.get("remote", "hybrid")
    for field in PACKAGE_FIELDS:
        if field == "remote":
            continue
        try:
            package[field] = float(package[field])
        except (TypeError, ValueError):
            package[field] = float(fallback.get(field, 0) or 0)
    return package


# ---------------------------------------------------------------------------
# Parallel package state machine — mirrors app.offercheck.negotiation exactly
# in shape (turn alternation, max rounds, terminal states); can't share the
# same functions since RoundEntry.value there is a float, not a package dict.
# ---------------------------------------------------------------------------

PACKAGE_TERMINAL_STATES = {"AGREED", "WALKAWAY", "EXPIRED"}

_PACKAGE_TURN_BY_STATE = {
    "PENDING_EMPLOYER": "employer",
    "EMPLOYER_RESPONDED": "candidate",
    "CANDIDATE_COUNTERED": "employer",
}


class PackageNotReady(Exception):
    """Raised when a session is missing the sealed package inputs this mode needs."""


def package_current_turn(session: "Session") -> str | None:
    return _PACKAGE_TURN_BY_STATE.get(session.package_state)


def apply_package_move(session: "Session", actor: str, move: str, package: dict | None) -> None:
    if session.package_state in PACKAGE_TERMINAL_STATES:
        raise ValueError(f"package session is in state {session.package_state}")

    turn = package_current_turn(session)
    if turn != actor:
        raise ValueError(f"it is not {actor}'s turn (package mode)")

    if move == "counter" and not package:
        raise ValueError("a package is required for a counter")

    session.package_round_number += 1
    history_entry = {"round": session.package_round_number, "actor": actor, "move": move, "package": package}
    session.package_history.append(history_entry)

    if move == "accept":
        session.package_agreed = session.candidate_current_package if actor == "employer" else session.employer_current_package
        session.package_state = "AGREED"
    elif move == "walk":
        session.package_state = "WALKAWAY"
    else:  # counter
        if actor == "candidate":
            session.candidate_current_package = package
            session.package_state = "CANDIDATE_COUNTERED"
        else:
            session.employer_current_package = package
            session.package_state = "EMPLOYER_RESPONDED"
        if session.package_round_number >= session.max_rounds:
            session.package_state = "EXPIRED"


# ---------------------------------------------------------------------------
# Attestation — mirrors app.offercheck.negotiation.attested_terms()
# ---------------------------------------------------------------------------

def _package_hash(package: dict | None) -> str | None:
    if package is None:
        return None
    return hashlib.sha256(json.dumps(package, sort_keys=True).encode()).hexdigest()


def attested_package_terms(session: "Session", credential_hash: str | None = None) -> dict:
    """
    Payload whose SHA-256 digest is bound into the TDX quote's report_data
    for a package-mode session. Same discipline as negotiation.attested_terms():
    the private opening package and band-derived bounds are hashed, not
    included in the clear; the agreed package (once a deal closes) is the
    disclosed outcome both sides already know, so it's included as-is.
    """
    terms = {
        "session_id": session.id,
        "package_state": session.package_state,
        "package_round_number": session.package_round_number,
        "package_agreed": session.package_agreed,
        "candidate_package_ask_hash": _package_hash(session.candidate_package_ask),
        "consistency_verified": session.consistency.verified,
    }
    if credential_hash is not None:
        terms["credential_hash"] = credential_hash
    return terms
