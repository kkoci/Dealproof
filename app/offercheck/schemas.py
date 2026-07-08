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
    ats_candidate_ref: str | None = None  # Phase 3: candidate/opportunity id in the company's ATS, if known
    candidate_floor: float | None = Field(default=None, gt=0, description="Sealed — only used if agentic negotiation is triggered; never returned")
    candidate_priorities: str | None = None  # Phase 2A: sealed, free text (e.g. "base matters more than equity")


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
    employer_authority_limit: float | None = Field(default=None, gt=0, description="Sealed — only used if agentic negotiation is triggered; never returned")
    employer_priorities: str | None = None  # Phase 2A: sealed, free text (e.g. "equity is more flexible than base")


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


class AttestationReceipt(BaseModel):
    """
    TDX attestation receipt for a closed session (Phase 2). Never contains
    raw candidate/employer numbers — only hashes of the private inputs plus
    the publicly-known outcome. See app.offercheck.negotiation.attested_terms.
    """
    session_id: str
    state: SessionState
    round_number: int
    agreed_price: float | None
    competing_offer_hash: str
    employer_band_hash: str | None
    credential_hash: str | None = None  # Phase 3: OfferVerifiedCredential hash, folded into this same quote
    attestation: str
    tee_attested: bool
    tee_mode: str


class DcapVerification(BaseModel):
    """Parsed DCAP quote fields for an offercheck attestation — mirrors app.tee.dcap.parse_tdx_quote."""
    session_id: str
    mode: str
    version: int | None = None
    tee_type: str | None = None
    qe_vendor_id: str | None = None
    report_data_hex: str | None = None
    deal_terms_hash: str | None = None
    cert_chain_valid: bool | None = None
    qe_sig_valid: bool | None = None
    att_key_binding_valid: bool | None = None
    td_sig_valid: bool | None = None
    intel_verified: bool = False
    pck_cert_subject: str | None = None
    verification_status: str
    error: str | None = None


class ExtractedOfferFields(BaseModel):
    """
    Draft fields from PDF extraction — deliberately unvalidated (base_salary
    may come back 0 on a low-confidence read). The candidate reviews/corrects
    these in the form before they ever reach the strict CompetingOffer model
    via POST /sessions.
    """
    company: str = ""
    role: str = ""
    base_salary: float = 0
    equity_value: float = 0
    bonus: float = 0
    start_date: str = ""


class OfferLetterExtraction(BaseModel):
    competing_offer: ExtractedOfferFields
    confidence: Literal["high", "medium", "low"]
    notes: list[str]


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
    agentic_ready: bool = False  # Phase 2A: True once both sides have sealed floor/authority_limit — booleans only, never the values


# ---------------------------------------------------------------------------
# Phase 3 — company auth, bulk verify, credential, ATS connection
# ---------------------------------------------------------------------------

Plan = Literal["individual", "team", "growth", "enterprise"]
AtsProvider = Literal["greenhouse", "lever", "workday"]


class CompanyRegisterRequest(BaseModel):
    name: str
    hires_per_year: int = Field(default=0, ge=0, description="Used only to recommend a plan")


class CompanyRegisterResponse(BaseModel):
    company_id: str
    api_key: str = Field(..., description="Shown exactly once — store it now, it cannot be recovered")
    recommended_plan: Plan
    pricing: dict


class AtsConnectRequest(BaseModel):
    provider: AtsProvider
    api_key: str


class AtsConnectResponse(BaseModel):
    company_id: str
    provider: AtsProvider
    connected: bool


class CredentialResponse(BaseModel):
    """πCreds-style conduct credential — see app.offercheck.credential."""
    session_id: str
    genuine_negotiation: bool
    round_count: int
    outcome: Literal["agreed", "walkaway", "expired"]
    issues: list[str]
    summary: str
    credential_hash: str
    tee_attested: bool


class BulkVerifyItem(BaseModel):
    competing_offer: CompetingOffer
    candidate_ask: float = Field(gt=0)
    ats_candidate_ref: str | None = None


class BulkVerifyRequest(BaseModel):
    verifications: list[BulkVerifyItem] = Field(..., min_length=1, max_length=50)


class BulkVerifyResult(BaseModel):
    session_id: str
    candidate_token: str
    employer_token: str
    employer_link: str
    consistency: ConsistencyCheck


class BulkVerifyResponse(BaseModel):
    company_id: str
    results: list[BulkVerifyResult]


class CompanySessionSummary(BaseModel):
    """Employer-side session listing for the TA dashboard. No candidate raw numbers."""
    session_id: str
    state: SessionState
    round_number: int
    gap_pct: float | None
    employer_link: str
    ats_candidate_ref: str | None = None


class CompanySessionsResponse(BaseModel):
    company_id: str
    sessions: list[CompanySessionSummary]


# ---------------------------------------------------------------------------
# Phase 2A — agentic negotiation (offercheck_phase2_spec.md)
# ---------------------------------------------------------------------------

class AgenticStartRequest(BaseModel):
    token: str  # either party's token — by this point both sides have already sealed their data privately


class AgenticRoundDetail(BaseModel):
    """
    One round of agent-vs-agent negotiation. Includes the offer amount — that
    IS this mode's contract (agents must know the number on the table to
    negotiate). What's never included, here or anywhere else: either side's
    sealed floor / band / authority limit, or either agent's reasoning.
    """
    round: int
    actor: Actor
    move: Move
    value: float | None


class AgenticResult(BaseModel):
    session_id: str
    state: SessionState
    agreed_price: float | None
    round_number: int
    transcript: list[AgenticRoundDetail]
    attestation: str | None
    tee_attested: bool
    credential: CredentialResponse | None = None
