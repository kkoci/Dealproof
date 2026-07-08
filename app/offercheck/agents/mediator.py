"""
Enclave mediator — Phase 2A agentic negotiation (see offercheck_phase2_spec.md).

Drives CandidateAgent + EmployerAgent through the SAME state machine
(app.offercheck.negotiation.apply_move) used by human-driven sessions, so an
agentic session gets identical turn-order, max-rounds-auto-expire, and
attestation/credential guarantees as a human one — the only thing that
changes is who decides each move.

The one deliberate difference from the human flow's privacy contract: within
this loop, each agent IS told the opposing side's current offer amount each
round (not just gap_pct) — that's this mode's own contract, spelled out in
offercheck_phase2_spec.md: "the offer number per round crosses the boundary,
nothing else." What never crosses, here or anywhere else in this vertical:
either side's sealed parameter (floor / band / authority limit), and either
agent's reasoning — each agent's own `history` list carries its own past
turns in full, but the opposing agent's turns stripped to {action, value}.

This "mediator" runs in the same FastAPI process as everything else in this
vertical — the same "the whole process already runs inside the TDX CVM in
production" reasoning documented in CLAUDE.md for Phase 2 attestation
applies here too. There is no separate enclave process to move this into.
"""
import logging

from app.offercheck import negotiation
from app.offercheck.agents.candidate_agent import CandidateAgent
from app.offercheck.agents.employer_agent import EmployerAgent
from app.offercheck.store import Session

logger = logging.getLogger(__name__)


class AgenticNotReady(Exception):
    """Raised when a session is missing the sealed inputs agentic mode needs."""


def _own_entry(role: str, decision: dict) -> dict:
    return {"role": role, "content": {"action": decision["action"], "value": decision["value"], "reasoning": decision.get("reasoning", "")}}


def _crossing_entry(role: str, decision: dict) -> dict:
    """What actually crosses the boundary: action + value. Never reasoning."""
    return {"role": role, "content": {"action": decision["action"], "value": decision["value"]}}


def build_agents(session: Session) -> tuple[CandidateAgent, EmployerAgent]:
    """
    Checks the session has both sides' sealed inputs, then constructs the
    two agents. Split out from run_agentic_negotiation() so callers (and
    tests) can construct agents, patch their `.client.messages.create`
    directly — the same pattern app/agents/negotiation.py's tests use for
    BuyerAgent/SellerAgent — then drive the loop separately.
    """
    if session.candidate_floor is None:
        raise AgenticNotReady("candidate has not sealed a floor for this session")
    if not session.band_set or session.employer_authority_limit is None:
        raise AgenticNotReady("employer has not sealed a band/authority limit for this session")

    candidate_agent = CandidateAgent(
        opening_ask=session.candidate_ask,
        floor=session.candidate_floor,
        priorities=session.candidate_priorities or "",
        competing_offer_summary=f"{session.competing_offer.company} {session.competing_offer.role}",
    )
    employer_agent = EmployerAgent(
        band_min=session.band_min,
        band_mid=session.band_mid,
        band_max=min(session.band_max, session.employer_authority_limit),
        priorities=session.employer_priorities or "",
    )
    return candidate_agent, employer_agent


async def run_agentic_negotiation(session: Session, candidate_agent: CandidateAgent, employer_agent: EmployerAgent) -> list[dict]:
    """
    Runs CandidateAgent vs EmployerAgent to completion (ACCEPT/WALK, or
    max_rounds auto-expiry). Mutates `session` in place via the real state
    machine. Returns a transcript safe to hand back to the API caller:
    [{"round": int, "actor": "candidate"|"employer", "move": str, "value": float|None}, ...]
    — amounts included (this mode's contract), reasoning is not.
    """
    session.agentic_mode = True

    candidate_history: list[dict] = []
    employer_history: list[dict] = []
    transcript: list[dict] = []

    while session.state not in negotiation.TERMINAL_STATES:
        turn = negotiation.current_turn(session)
        round_number = session.round_number + 1

        if turn == "employer":
            decision = await employer_agent.decide(session.candidate_ask, employer_history)
            employer_history.append(_own_entry("employer", decision))
            candidate_history.append(_crossing_entry("employer", decision))
            negotiation.apply_move(session, actor="employer", move=decision["action"], value=decision.get("value"))
            actor = "employer"
        else:
            decision = await candidate_agent.decide(session.employer_current_offer, candidate_history)
            candidate_history.append(_own_entry("candidate", decision))
            employer_history.append(_crossing_entry("candidate", decision))
            negotiation.apply_move(session, actor="candidate", move=decision["action"], value=decision.get("value"))
            actor = "candidate"

        logger.info(f"session {session.id} agentic round {round_number}: {actor} {decision['action']}")
        transcript.append({
            "round": round_number,
            "actor": actor,
            "move": decision["action"],
            "value": decision.get("value") if decision["action"] == "counter" else None,
        })

    return transcript
