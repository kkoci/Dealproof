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


class OfferPackage(BaseModel):
    """Phase 2B (offercheck_phase2_spec.md) — a full compensation package, exchanged whole each round."""
    base: float = Field(gt=0)
    equity_grant: float = Field(default=0.0, ge=0)
    vesting_years: float = Field(default=4.0, gt=0)
    cliff_months: float = Field(default=12.0, ge=0)
    signing_bonus: float = Field(default=0.0, ge=0)
    annual_bonus_pct: float = Field(default=0.0, ge=0)
    remote: Literal["remote", "hybrid", "onsite"] = "hybrid"
    start_date_days: float = Field(default=30.0, ge=0)
    pto_days: float = Field(default=15.0, ge=0)


class CandidateSubmitRequest(BaseModel):
    competing_offer: CompetingOffer
    candidate_ask: float = Field(gt=0)
    ats_candidate_ref: str | None = None  # Phase 3: candidate/opportunity id in the company's ATS, if known
    candidate_floor: float | None = Field(default=None, gt=0, description="Sealed — only used if agentic negotiation is triggered; never returned")
    candidate_priorities: str | None = None  # Phase 2A: sealed, free text (e.g. "base matters more than equity")
    # Phase 2B: full compensation package negotiation — all optional, sealed, never returned
    candidate_package_ask: OfferPackage | None = None
    candidate_total_comp_floor: float | None = Field(default=None, gt=0)
    candidate_package_priorities: str | None = None


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
    employer_total_comp_budget: float | None = Field(default=None, gt=0, description="Phase 2B: sealed total-comp ceiling; never returned")


class EmployerBandResponse(BaseModel):
    session_id: str
    state: SessionState
    band_set: bool
    gap_pct: float  # (candidate_ask - band_mid) / band_mid * 100 — the only number the employer sees


class CandidateEnableAgenticRequest(BaseModel):
    """
    Seals candidate_floor after session creation — see PATCH .../candidate/enable-agentic.
    Same field, same "sealed, never returned" contract as CandidateSubmitRequest.candidate_floor;
    this just lets it be set later instead of only at the one-shot POST /sessions moment.
    """
    token: str
    candidate_floor: float = Field(gt=0)
    candidate_priorities: str | None = None


class EmployerEnableAgenticRequest(BaseModel):
    """Seals employer_authority_limit after the band has already been set — see PATCH .../employer/enable-agentic."""
    token: str
    employer_authority_limit: float = Field(gt=0)
    employer_priorities: str | None = None


class CandidateEnablePackageAgenticRequest(BaseModel):
    """
    Package-mode counterpart to CandidateEnableAgenticRequest — seals candidate_total_comp_floor
    (the only number the UI asks for) after session creation. candidate_package_ask (the full
    opening package PackageCandidateAgent needs) is synthesized server-side from the candidate's
    existing candidate_ask as base plus neutral defaults for every other term — see
    routes.py::enable_candidate_package_agentic for the exact defaults.
    """
    token: str
    candidate_total_comp_floor: float = Field(gt=0)
    candidate_package_priorities: str | None = None


class EmployerEnablePackageAgenticRequest(BaseModel):
    """Package-mode counterpart to EmployerEnableAgenticRequest — seals employer_total_comp_budget
    after the band has already been set. Unlike the candidate side, no package synthesis is needed
    here — PackageEmployerAgent only ever needs band_min/mid/max (already set) + this budget."""
    token: str
    employer_total_comp_budget: float = Field(gt=0)
    employer_priorities: str | None = None


class MoveRequest(BaseModel):
    token: str
    move: Move
    value: float | None = None  # required when move == "counter"


class RoundSummary(BaseModel):
    round_number: int
    actor: Actor
    move: Move
    value: float | None = None  # populated only when session.agentic_mode — see routes._view_for


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


class PackageRoundDetail(BaseModel):
    """
    One round of package-vs-package negotiation. Includes the full package —
    that IS this mode's contract, same reasoning as AgenticRoundDetail.value.
    Never included: either side's sealed floor/budget, or agent reasoning.
    Safe to expose cross-party unconditionally (unlike RoundSummary.value):
    package negotiation is agentic-only (see app.offercheck.package's module
    docstring), so every package_history entry already crossed the agent
    boundary by construction — there's no human-only package mode to protect.
    """
    round: int
    actor: Actor
    move: Move
    package: OfferPackage | None
    total_comp: float | None  # total_comp_value(package) — convenience for the frontend table


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
    my_agentic_sealed: bool = False  # True once the viewer's own side has sealed their floor/authority_limit — lets the UI hide its own "enable AI negotiation" prompt without exposing the other side's status
    package_agentic_ready: bool = False  # Phase 2B: True once both sides have sealed package_ask/total_comp_floor + budget
    # Package-mode progress (Phase 2B) — a parallel channel to state/round_number/turn/history
    # above (see app.offercheck.package's module docstring for why it's parallel, not merged).
    # Exposed here so polling clients can render live package-negotiation progress; before this,
    # SessionView had no package-mode fields at all, so a party watching a package AI negotiation
    # via GET /sessions/{id} never saw it advance past whatever the scalar state was.
    package_state: SessionState = "PENDING_EMPLOYER"
    package_round_number: int = 0
    package_turn: Actor | None = None  # None when package_state is terminal
    package_history: list[PackageRoundDetail] = Field(default_factory=list)
    package_agreed_package: OfferPackage | None = None
    my_package_agentic_sealed: bool = False  # viewer's own side has sealed candidate_total_comp_floor / employer_total_comp_budget
    package_converged_hint: bool = False  # candidate/employer current packages are within 2% total comp — same threshold package_mediator uses to nudge agents toward accepting


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
# Employer-initiated invites — mirror image of the candidate-initiated flow
# above (POST /sessions). An authenticated company opens a negotiation before
# any candidate/Session exists; a Session is only ever created at claim time.
# ---------------------------------------------------------------------------

InviteStatus = Literal["PENDING_CANDIDATE", "CLAIMED"]


class EmployerInviteRequest(BaseModel):
    band_min: float = Field(gt=0)
    band_mid: float = Field(gt=0)
    band_max: float = Field(gt=0)
    requirements: str | None = None  # free text for the employer's own dashboard — never shown to the candidate
    ats_candidate_ref: str | None = None
    employer_authority_limit: float | None = Field(default=None, gt=0, description="Sealed — only used if agentic negotiation is triggered; never returned")
    employer_priorities: str | None = None


class EmployerInviteResponse(BaseModel):
    invite_id: str
    candidate_join_link: str
    status: InviteStatus


class InviteStatusResponse(BaseModel):
    """
    employer_token is populated only once the invite is CLAIMED. Safe to
    return here because this endpoint requires the owning company's
    X-API-Key — the same trust boundary that already gates every other
    company-scoped read in this vertical.
    """
    invite_id: str
    status: InviteStatus
    session_id: str | None = None
    employer_token: str | None = None


class CandidateJoinRequest(BaseModel):
    competing_offer: CompetingOffer
    candidate_ask: float = Field(gt=0)
    candidate_floor: float | None = Field(default=None, gt=0, description="Sealed — only used if agentic negotiation is triggered; never returned")
    candidate_priorities: str | None = None


# ---------------------------------------------------------------------------
# Phase 2A — agentic negotiation (offercheck_phase2_spec.md)
# ---------------------------------------------------------------------------

class AgenticStartRequest(BaseModel):
    # A party token (candidate_token/employer_token) OR a valid X-Demo-Token header is required —
    # see app.offercheck.demo_auth. token is optional here specifically for the demo-token-only path
    # (a spectator with a magic link but no party token, e.g. POST /auth/demo-link recipients).
    token: str | None = None


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


# ---------------------------------------------------------------------------
# Magic-link auth (see app.offercheck.demo_auth) — gates Claude-calling endpoints
# ---------------------------------------------------------------------------

class DemoLinkRequest(BaseModel):
    session_id: str
    expires_hours: float = Field(default=24.0, gt=0, le=168, description="Max 7 days")


class DemoLinkResponse(BaseModel):
    demo_url: str
    token: str
    expires_at: str  # ISO-8601 UTC


class VerifyTokenResponse(BaseModel):
    valid: bool
    session_id: str
    expires_at: str  # ISO-8601 UTC


# ---------------------------------------------------------------------------
# Phase 2B — full compensation package negotiation (offercheck_phase2_spec.md)
# ---------------------------------------------------------------------------

class PackageCredentialResponse(BaseModel):
    session_id: str
    genuine_negotiation: bool
    round_count: int
    outcome: Literal["agreed", "walkaway", "expired"]
    issues: list[str]
    summary: str
    credential_hash: str
    tee_attested: bool


class PackageAgenticResult(BaseModel):
    session_id: str
    state: SessionState
    agreed_package: OfferPackage | None
    round_number: int
    transcript: list[PackageRoundDetail]
    attestation: str | None
    tee_attested: bool
    credential: PackageCredentialResponse | None = None
