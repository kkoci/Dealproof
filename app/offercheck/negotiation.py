"""
Revision-loop state machine — the core product (see build_spec_offer_check.md).

Pure functions operating on an in-memory Session (app.offercheck.store). No
I/O, no LLM, no TEE — Phase 1 is deliberately dependency-free so the flow can
be validated before trust infrastructure is added in Phase 2.

States: PENDING_EMPLOYER -> EMPLOYER_RESPONDED <-> CANDIDATE_COUNTERED -> AGREED | WALKAWAY | EXPIRED
Turn order: employer moves first (after setting their private band), then
alternates. Max 5 rounds; the 5th unresolved counter auto-expires the session.
"""
from app.offercheck.store import RoundEntry, Session

TERMINAL_STATES = {"AGREED", "WALKAWAY", "EXPIRED"}

_TURN_BY_STATE = {
    "PENDING_EMPLOYER": "employer",
    "EMPLOYER_RESPONDED": "candidate",
    "CANDIDATE_COUNTERED": "employer",
}


class OfferCheckError(Exception):
    """Base class for state-machine violations; routes.py maps these to HTTP codes."""


class InvalidToken(OfferCheckError):
    pass


class SessionTerminal(OfferCheckError):
    pass


class WrongTurn(OfferCheckError):
    pass


class BandAlreadySet(OfferCheckError):
    pass


class BandNotSet(OfferCheckError):
    pass


class InvalidMove(OfferCheckError):
    pass


def current_turn(session: Session) -> str | None:
    return _TURN_BY_STATE.get(session.state)


def band_gap_pct(candidate_ask: float, band_mid: float) -> float:
    return (candidate_ask - band_mid) / band_mid * 100


def live_gap_pct(session: Session) -> float | None:
    if session.employer_current_offer is None:
        return None
    return (session.candidate_ask - session.employer_current_offer) / session.employer_current_offer * 100


def set_employer_band(session: Session, band_min: float, band_mid: float, band_max: float) -> float:
    """Stores the employer's private band and returns the one-time gap preview."""
    if session.state != "PENDING_EMPLOYER":
        raise SessionTerminal(f"session is in state {session.state}")
    if session.band_set:
        raise BandAlreadySet("employer band has already been submitted for this session")

    session.band_min = band_min
    session.band_mid = band_mid
    session.band_max = band_max
    session.band_set = True
    return band_gap_pct(session.candidate_ask, band_mid)


def apply_move(session: Session, actor: str, move: str, value: float | None) -> None:
    if session.state in TERMINAL_STATES:
        raise SessionTerminal(f"session is in state {session.state}")

    turn = current_turn(session)
    if turn != actor:
        raise WrongTurn(f"it is not {actor}'s turn")

    if actor == "employer" and not session.band_set:
        raise BandNotSet("employer must submit their salary band before moving")

    if move == "counter" and (value is None or value <= 0):
        raise InvalidMove("a positive value is required for a counter")

    session.round_number += 1
    session.history.append(RoundEntry(round_number=session.round_number, actor=actor, move=move))

    if move == "accept":
        session.agreed_price = session.candidate_ask if actor == "employer" else session.employer_current_offer
        session.state = "AGREED"
    elif move == "walk":
        session.state = "WALKAWAY"
    else:  # counter
        if actor == "candidate":
            session.candidate_ask = value
            session.state = "CANDIDATE_COUNTERED"
        else:
            session.employer_current_offer = value
            session.state = "EMPLOYER_RESPONDED"
        if session.round_number >= session.max_rounds:
            session.state = "EXPIRED"
