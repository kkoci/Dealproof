"""
Pydantic schemas for the Offer Check vertical (Phase 1 — no TEE, no DB).

Privacy constraints (non-negotiable, see build_spec_offer_check.md):
  - The employer's salary band (min/mid/max) is never returned in any
    response the candidate can see.
  - The candidate's raw competing-offer details and raw ask are never
    returned in any response the employer can see.
  - Cross-party responses expose only: state, round_number, gap_pct, and
    the other party's move (accept | counter | walk). Never a raw number
    belonging to the other party.
"""
from typing import Literal

from pydantic import BaseModel, Field

Move = Literal["accept", "counter", "walk"]
SessionState = Literal[
    "PENDING_EMPLOYER",
    "EMPLOYER_RESPONDED",
    "CANDIDATE_COUNTERED",
    "AGREED",
    "WALKAWAY",
    "EXPIRED",
]
Actor = Literal["candidate", "employer"]


class CompetingOffer(BaseModel):
    company: str
    role: str
    base_salary: float = Field(gt=0)
    equity_value: float = Field(default=0.0, ge=0)   # annualized estimate
    bonus: float = Field(default=0.0, ge=0)
    start_date: str  # ISO-8601 date, e.g. "2026-09-01"


class ConsistencyCheck(BaseModel):
    verified: bool
    issues: list[str]


class CandidateSubmitRequest(BaseModel):
    competing_offer: CompetingOffer
    candidate_ask: float = Field(gt=0)


class CandidateSubmitResponse(BaseModel):
    session_id: str
    candidate_token: str
    employer_token: str
    employer_link: str
    state: SessionState
    consistency: ConsistencyCheck


class EmployerBandRequest(BaseModel):
    employer_token: str
    band_min: float = Field(gt=0)
    band_mid: float = Field(gt=0)
    band_max: float = Field(gt=0)


class EmployerBandResponse(BaseModel):
    session_id: str
    state: SessionState
    band_set: bool
    gap_pct: float  # (candidate_ask - band_mid) / band_mid * 100 — the only number the employer sees


class MoveRequest(BaseModel):
    token: str
    move: Move
    value: float | None = None  # required when move == "counter"


class RoundSummary(BaseModel):
    round_number: int
    actor: Actor
    move: Move


class SessionView(BaseModel):
    """Viewer-scoped snapshot. Never includes the other party's raw numbers."""
    session_id: str
    state: SessionState
    round_number: int
    max_rounds: int
    turn: Actor | None  # None when terminal
    band_set: bool
    gap_pct: float | None
    history: list[RoundSummary]
    consistency: ConsistencyCheck
    agreed_price: float | None = None
    # Only populated for the viewer's own side:
    my_current_value: float | None = None
