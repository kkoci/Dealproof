"""
Package mediator — Phase 2B agentic package negotiation (see
offercheck_phase2_spec.md). Mirrors app.offercheck.agents.mediator exactly in
shape; drives the parallel package state machine (app.offercheck.package)
instead of the scalar one, since a full package can't flow through
negotiation.apply_move()'s float `value`.

Same privacy contract as Phase 2A: each agent IS told the opposing side's
current package every round (that's this mode's contract — you need the
whole package on the table to negotiate trade-offs across terms), but sealed
floors/budget and either agent's reasoning never cross. Same "runs in the
same process that's already inside the TDX CVM in production" reasoning as
everywhere else in this vertical — no separate enclave process.
"""
import logging

from app.offercheck import demo_auth
from app.offercheck.agents.package_candidate_agent import PackageCandidateAgent
from app.offercheck.agents.package_employer_agent import PackageEmployerAgent
from app.offercheck.package import PackageNotReady, apply_package_move, is_converged, package_current_turn, total_comp_value
from app.offercheck.store import Session

logger = logging.getLogger(__name__)

PACKAGE_TERMINAL_STATES = {"AGREED", "WALKAWAY", "EXPIRED"}


def _own_entry(role: str, decision: dict) -> dict:
    return {"role": role, "content": {"action": decision["action"], "package": decision["package"], "reasoning": decision.get("reasoning", "")}}


def _crossing_entry(role: str, decision: dict) -> dict:
    """What actually crosses the boundary: action + package. Never reasoning."""
    return {"role": role, "content": {"action": decision["action"], "package": decision["package"]}}


def _currently_converged(session: Session) -> bool:
    """
    Deterministic convergence check, computed in code (not left to the LLM
    to notice) — "total comp within 2% => suggest accept" per
    offercheck_phase2_spec.md's Phase 2B acceptance criteria. Only meaningful
    once both sides have a current package on the table (i.e. not round 1,
    before the employer has made an opening move).
    """
    if session.candidate_current_package is None or session.employer_current_package is None:
        return False
    return is_converged(
        total_comp_value(session.candidate_current_package),
        total_comp_value(session.employer_current_package),
    )


def build_package_agents(session: Session) -> tuple[PackageCandidateAgent, PackageEmployerAgent]:
    """
    Checks the session has both sides' sealed package inputs, then constructs
    the two agents. Split out for testability — see mediator.build_agents()'s
    docstring for why (patch anthropic.AsyncAnthropic by module path does not
    give two agent classes independently different mocks).
    """
    if session.candidate_package_ask is None or session.candidate_total_comp_floor is None:
        raise PackageNotReady("candidate has not sealed a package ask/total-comp floor for this session")
    if not session.band_set or session.employer_total_comp_budget is None:
        raise PackageNotReady("employer has not sealed a band/total-comp budget for this session")

    candidate_agent = PackageCandidateAgent(
        opening_package=session.candidate_package_ask,
        base_floor=session.candidate_floor or session.band_min,
        total_comp_floor=session.candidate_total_comp_floor,
        priorities=session.candidate_package_priorities or "",
        competing_package_summary=f"{session.competing_offer.company} {session.competing_offer.role}",
    )
    employer_base_max = min(session.band_max, session.employer_authority_limit or session.band_max)
    employer_agent = PackageEmployerAgent(
        base_min=session.band_min,
        base_max=employer_base_max,
        total_comp_budget=session.employer_total_comp_budget,
        priorities=session.employer_priorities or "",
    )
    return candidate_agent, employer_agent


async def run_package_negotiation(
    session: Session, candidate_agent: PackageCandidateAgent, employer_agent: PackageEmployerAgent
) -> list[dict]:
    """
    Runs PackageCandidateAgent vs PackageEmployerAgent to completion (ACCEPT/
    WALK, or max_rounds auto-expiry). Mutates `session` in place via
    app.offercheck.package.apply_package_move(). Returns a transcript safe to
    hand back to the API caller — full packages included (this mode's
    contract), reasoning is not.
    """
    candidate_history: list[dict] = []
    employer_history: list[dict] = []
    transcript: list[dict] = []

    while session.package_state not in PACKAGE_TERMINAL_STATES:
        turn = package_current_turn(session)
        round_number = session.package_round_number + 1

        demo_auth.record_and_check_spend(session.id)
        converged = _currently_converged(session)

        if turn == "employer":
            decision = await employer_agent.decide(session.candidate_current_package, employer_history, converged_hint=converged)
            employer_history.append(_own_entry("employer", decision))
            candidate_history.append(_crossing_entry("employer", decision))
            apply_package_move(session, actor="employer", move=decision["action"], package=decision.get("package"))
            actor = "employer"
        else:
            decision = await candidate_agent.decide(session.employer_current_package, candidate_history, converged_hint=converged)
            candidate_history.append(_own_entry("candidate", decision))
            employer_history.append(_crossing_entry("candidate", decision))
            apply_package_move(session, actor="candidate", move=decision["action"], package=decision.get("package"))
            actor = "candidate"

        logger.info(f"session {session.id} package round {round_number}: {actor} {decision['action']}")
        package = decision.get("package") if decision["action"] == "counter" else None
        transcript.append({
            "round": round_number,
            "actor": actor,
            "move": decision["action"],
            "package": package,
            "total_comp": total_comp_value(package) if package else None,
        })

    return transcript
