"""
In-memory session store — Phase 1 POC (no auth, no database; see
build_spec_offer_check.md Decision 4). Sessions live for the lifetime of the
process. Phase 3 replaces this with persisted, company-authenticated storage.
"""
import secrets
from dataclasses import dataclass, field

from app.offercheck.schemas import CompetingOffer, ConsistencyCheck

MAX_ROUNDS = 5


@dataclass
class RoundEntry:
    round_number: int
    actor: str
    move: str


@dataclass
class Session:
    id: str
    candidate_token: str
    employer_token: str
    competing_offer: CompetingOffer
    consistency: ConsistencyCheck
    candidate_ask: float
    state: str = "PENDING_EMPLOYER"
    round_number: int = 0
    max_rounds: int = MAX_ROUNDS
    band_min: float | None = None
    band_mid: float | None = None
    band_max: float | None = None
    band_set: bool = False
    employer_current_offer: float | None = None
    agreed_price: float | None = None
    history: list[RoundEntry] = field(default_factory=list)
    attestation: str | None = None


_SESSIONS: dict[str, Session] = {}


def reset() -> None:
    """Test-only: clear all sessions between test cases."""
    _SESSIONS.clear()


def create_session(competing_offer: CompetingOffer, candidate_ask: float, consistency: ConsistencyCheck) -> Session:
    session = Session(
        id=secrets.token_urlsafe(12),
        candidate_token=secrets.token_urlsafe(16),
        employer_token=secrets.token_urlsafe(16),
        competing_offer=competing_offer,
        consistency=consistency,
        candidate_ask=candidate_ask,
    )
    _SESSIONS[session.id] = session
    return session


def get_session(session_id: str) -> Session | None:
    return _SESSIONS.get(session_id)
