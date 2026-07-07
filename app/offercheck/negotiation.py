"""
Revision-loop state machine — the core product (see build_spec_offer_check.md).

Pure functions operating on an in-memory Session (app.offercheck.store). No
I/O, no LLM, no TEE — Phase 1 is deliberately dependency-free so the flow can
be validated before trust infrastructure is added in Phase 2. Phase 2 adds
attestation (below): the terms are hashed here, but the actual TDX quote
request happens in routes.py, which is the only I/O boundary.

States: PENDING_EMPLOYER -> EMPLOYER_RESPONDED <-> CANDIDATE_COUNTERED -> AGREED | WALKAWAY | EXPIRED
Turn order: employer moves first (after setting their private band), then
alternates. Max 5 rounds; the 5th unresolved counter auto-expires the session.
"""
import hashlib
import json

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
    round_value = value if move == "counter" else None
    session.history.append(RoundEntry(round_number=session.round_number, actor=actor, move=move, value=round_value))

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


# ---------------------------------------------------------------------------
# Attestation (Phase 2) — hashing only; routes.py owns the tappd I/O call.
# ---------------------------------------------------------------------------

def competing_offer_hash(session: Session) -> str:
    payload = {
        "company": session.competing_offer.company,
        "role": session.competing_offer.role,
        "base_salary": session.competing_offer.base_salary,
        "equity_value": session.competing_offer.equity_value,
        "bonus": session.competing_offer.bonus,
        "start_date": session.competing_offer.start_date,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def employer_band_hash(session: Session) -> str | None:
    if not session.band_set:
        return None
    payload = {"band_min": session.band_min, "band_mid": session.band_mid, "band_max": session.band_max}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def attested_terms(session: Session, credential_hash: str | None = None) -> dict:
    """
    The payload whose SHA-256 digest is bound into the TDX quote's report_data.

    Deliberately excludes every raw number: only hashes of the private
    competing-offer and employer-band inputs are included, alongside the
    publicly-known outcome (state, round count, agreed price). A verifier can
    confirm the outcome is genuine and, if either party later chooses to
    disclose their raw inputs, confirm those inputs match what was attested —
    without the quote itself ever exposing them.

    credential_hash (Phase 3): the OfferVerifiedCredential's hash, computed by
    routes.py before signing so the conduct credential is itself covered by
    the same TDX quote — mirroring core DealProof's Step P (πCreds) landing
    in report_data before the final Step A re-attest.
    """
    terms = {
        "session_id": session.id,
        "state": session.state,
        "round_number": session.round_number,
        "agreed_price": session.agreed_price,
        "consistency_verified": session.consistency.verified,
        "competing_offer_hash": competing_offer_hash(session),
        "employer_band_hash": employer_band_hash(session),
    }
    if credential_hash is not None:
        terms["credential_hash"] = credential_hash
    return terms
