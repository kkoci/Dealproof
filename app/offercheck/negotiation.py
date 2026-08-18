"""
Revision-loop state machine — the core product (see build_spec_offer_check.md).

Pure functions operating on an in-memory Session (app.offercheck.store). No
I/O, no LLM, no TEE — Phase 1 is deliberately dependency-free so the flow can
be validated before trust infrastructure is added in Phase 2. Phase 2 adds
attestation (below): the terms are hashed here, but the actual TDX quote
request happens in routes.py, which is the only I/O boundary.

States: PENDING_EMPLOYER -> EMPLOYER_RESPONDED <-> CANDIDATE_COUNTERED -> PENDING_APPROVAL -> AGREED
                                                                       -> WALKAWAY | EXPIRED (direct, unaffected by the approval stage)
                                                        PENDING_APPROVAL -> DECLINED | STALEMATE
Turn order: employer moves first (after setting their private band), then
alternates. Max 5 rounds; the 5th unresolved counter auto-expires the session.

Approval stage: an "accept" no longer lands on AGREED directly — it lands on
PENDING_APPROVAL, a human-only checkpoint (see apply_approval_vote()) where
each party casts exactly one vote: "approve" | "request_more_rounds" |
"decline". This is deliberate and intentionally the *only* human touchpoint
in an otherwise-agentic negotiation — the agents still decide every round
autonomously; a human only ever weighs in once, after the agents reach an
outcome, to approve/reopen/decline it. See app.offercheck.agents.mediator's
module docstring for why the agentic loop itself stops at PENDING_APPROVAL
rather than voting on the human's behalf.

Resolution rule, evaluated after every vote (not just once both are in):
  - either side votes "decline"                     -> DECLINED, immediately,
    even before the other side has voted at all. Decline is a unilateral veto,
    never something that waits on the other party.
  - both votes recorded, at least one "request_more_rounds", none declined
    -> reopen: the session resumes ordinary negotiation for another round
    budget (see MAX_EXTENSIONS), with the side that did NOT ask for more
    rounds moving next. Exhausting MAX_EXTENSIONS without a clean double-
    approve -> STALEMATE instead of another reopen.
  - both votes recorded and both "approve"           -> AGREED, genuinely
    terminal now — this is the point attestation actually fires (see
    routes.py's new .../approval endpoints, which call _maybe_attest just
    like every other terminal-reaching call site already does).
This "recompute on every vote" shape is what makes the decline-always-wins /
request_more_rounds-beats-approve precedence hold regardless of arrival
order, without needing any actual concurrency handling — a decline is
checked first, unconditionally, on every call, so it can never lose a race
with a same-request "simultaneous" vote from the other side.
"""
import hashlib
import json

from app.offercheck.constants import MAX_EXTENSIONS, MAX_ROUNDS
from app.offercheck.integrations.market_data import MarketRange
from app.offercheck.store import RoundEntry, Session

TERMINAL_STATES = {"AGREED", "WALKAWAY", "EXPIRED", "DECLINED", "STALEMATE"}

_TURN_BY_STATE = {
    "PENDING_EMPLOYER": "employer",
    "EMPLOYER_RESPONDED": "candidate",
    "CANDIDATE_COUNTERED": "employer",
}
# Deliberately no PENDING_APPROVAL entry: it isn't a single-actor's-turn state — both
# parties may vote independently, see apply_approval_vote() — so current_turn() correctly
# returns None there, same as it does for the other terminal states.


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


class NotPendingApproval(OfferCheckError):
    pass


class AlreadyVoted(OfferCheckError):
    pass


class ProvenanceCredentialRequired(OfferCheckError):
    pass


def current_turn(session: Session) -> str | None:
    return _TURN_BY_STATE.get(session.state)


def band_gap_pct(candidate_ask: float, band_mid: float) -> float:
    return (candidate_ask - band_mid) / band_mid * 100


def live_gap_pct(session: Session) -> float | None:
    if session.employer_current_offer is None:
        return None
    return (session.candidate_ask - session.employer_current_offer) / session.employer_current_offer * 100


def final_gap_pct(session: Session) -> float | None:
    """
    How far the agreed price moved from the employer's opening counter —
    an external anchor the candidate agent never controls, unlike a
    self-reported success metric. None until both an agreement exists and
    the employer actually countered at least once (an immediate employer
    accept never sets opening_employer_offer, see apply_move).
    """
    if session.agreed_price is None or session.opening_employer_offer is None:
        return None
    return (session.agreed_price - session.opening_employer_offer) / session.opening_employer_offer * 100


def market_percentile(session: Session, market_range: MarketRange | None) -> float | None:
    """
    Where agreed_price lands (0-100) within an external market comparator —
    an absolute anchor, complementing final_gap_pct's relative one (see that
    function's docstring). Unlike final_gap_pct, this can't be computed
    on-demand from session state alone: market_range comes from a network
    fetch (app.offercheck.integrations.market_data.fetch_market_range),
    called once at AGREED (see routes.py::_maybe_attest) — this function
    stays pure and synchronous, taking the already-fetched range as a
    parameter rather than fetching it itself, so it can be unit-tested and
    reasoned about with zero I/O.

    None if market_range is None (lookup failed, unconfigured, or unmatched
    role/location — see fetch_market_range's own resilience contract) or the
    session never actually reached an agreed_price.

    Piecewise-linear between p25/p50/p75, clamped to [0, 100] beyond the
    fetched range (an offer far outside p25-p75 is still "very low"/"very
    high", not an undefined value) and falling back to 50.0 ("at market") on
    a degenerate zero-width range rather than dividing by zero.
    """
    if session.agreed_price is None or market_range is None:
        return None

    price = session.agreed_price
    p25, p50, p75 = market_range.p25, market_range.p50, market_range.p75

    if price <= p50:
        span = p50 - p25
        pct = 50.0 if span == 0 else 25.0 + 25.0 * (price - p25) / span
    else:
        span = p75 - p50
        pct = 50.0 if span == 0 else 50.0 + 25.0 * (price - p50) / span

    return max(0.0, min(100.0, pct))


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

    if (
        actor == "candidate"
        and session.require_provenance_credential
        and session.candidate_provenance_credential is None
    ):
        raise ProvenanceCredentialRequired(
            "employer requires a verified git-provenance credential before the candidate can move"
        )

    if move == "counter" and (value is None or value <= 0):
        raise InvalidMove("a positive value is required for a counter")

    session.round_number += 1
    round_value = value if move == "counter" else None
    session.history.append(RoundEntry(round_number=session.round_number, actor=actor, move=move, value=round_value))

    if move == "accept":
        session.agreed_price = session.candidate_ask if actor == "employer" else session.employer_current_offer
        session.state = "PENDING_APPROVAL"
    elif move == "walk":
        session.state = "WALKAWAY"
    else:  # counter
        if actor == "candidate":
            session.candidate_ask = value
            session.state = "CANDIDATE_COUNTERED"
        else:
            if session.opening_employer_offer is None:
                session.opening_employer_offer = value
            session.employer_current_offer = value
            session.state = "EMPLOYER_RESPONDED"
        if session.round_number >= session.max_rounds:
            session.state = "EXPIRED"


def apply_approval_vote(session: Session, actor: str, decision: str) -> None:
    """
    Records one party's vote at the PENDING_APPROVAL checkpoint (see module
    docstring for the resolution rule) and resolves the outcome immediately
    if enough votes are in. `decision` is one of "approve" |
    "request_more_rounds" | "decline" — validated by the request schema, not
    re-validated here.
    """
    if session.state != "PENDING_APPROVAL":
        raise NotPendingApproval(f"session is not awaiting approval (state {session.state})")

    existing = session.candidate_approval_vote if actor == "candidate" else session.employer_approval_vote
    if existing is not None:
        raise AlreadyVoted(f"{actor} has already voted this approval cycle")

    if actor == "candidate":
        session.candidate_approval_vote = decision
    else:
        session.employer_approval_vote = decision

    session.approval_history.append({"cycle": session.extension_count + 1, "actor": actor, "decision": decision})
    _resolve_approval(session)


def _resolve_approval(session: Session) -> None:
    cand, emp = session.candidate_approval_vote, session.employer_approval_vote

    if cand == "decline" or emp == "decline":
        session.state = "DECLINED"
        session.agreed_price = None
        return

    if cand is None or emp is None:
        return  # only one vote in, and it wasn't a decline — wait for the other side

    if cand == "request_more_rounds" or emp == "request_more_rounds":
        if session.extension_count >= MAX_EXTENSIONS:
            session.state = "STALEMATE"
            session.agreed_price = None
            return
        session.extension_count += 1
        # The side that did NOT ask for more rounds moves next. If both did, there's no
        # non-requester — fall back to giving the move to whoever did *not* make the
        # original accept (i.e. resume the alternation as if the accept had been a
        # counter instead).
        if cand == "request_more_rounds" and emp != "request_more_rounds":
            next_actor = "employer"
        elif emp == "request_more_rounds" and cand != "request_more_rounds":
            next_actor = "candidate"
        else:
            acceptor = session.history[-1].actor if session.history else "candidate"
            next_actor = "employer" if acceptor == "candidate" else "candidate"
        session.candidate_approval_vote = None
        session.employer_approval_vote = None
        session.max_rounds += MAX_ROUNDS
        session.state = "EMPLOYER_RESPONDED" if next_actor == "candidate" else "CANDIDATE_COUNTERED"
        return

    # both approve
    session.state = "AGREED"


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

    market_percentile reads session.market_percentile directly rather than
    calling market_percentile(session, ...) here — by the time this function
    runs (routes.py::_maybe_attest, after the AGREED-transition fetch), the
    value is already computed and persisted; attested_terms() has no
    MarketRange to pass and must not trigger a fetch of its own (this stays
    a pure, I/O-free function like the rest of this module). Only the derived
    percentile is included — the raw fetched range is never persisted on
    Session at all, same discipline as opening_employer_offer never appearing
    here raw, only via final_gap_pct.
    """
    terms = {
        "session_id": session.id,
        "state": session.state,
        "round_number": session.round_number,
        "agreed_price": session.agreed_price,
        "final_gap_pct": final_gap_pct(session),
        "market_percentile": session.market_percentile,
        "consistency_verified": session.consistency.verified,
        "competing_offer_hash": competing_offer_hash(session),
        "employer_band_hash": employer_band_hash(session),
    }
    if credential_hash is not None:
        terms["credential_hash"] = credential_hash
    return terms
