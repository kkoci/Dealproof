"""
In-memory session store — still no database through Phase 3 (see
build_spec_offer_check.md Decision 4 and CLAUDE.md "Offer Check Architecture").
Sessions and companies (app.offercheck.auth) both live for the lifetime of
the process; a restart loses everything, including issued company API keys.
Acceptable for the current demo/POC scale — a real persistence migration is
tracked as a known gap, not silently done here.
"""
import secrets
from dataclasses import dataclass, field

from app.offercheck.constants import MAX_ROUNDS
from app.offercheck.credential import OfferVerifiedCredential, PackageCredential
from app.offercheck.schemas import CompetingOffer, ConsistencyCheck


@dataclass
class RoundEntry:
    round_number: int
    actor: str
    move: str
    value: float | None = None  # the actor's own submitted number on a counter — never exposed via SessionView


@dataclass
class Dispute:
    """
    A filed dispute against an AGREED session's outcome — see
    app.offercheck.disputes module docstring for the full design (two
    dispute types, why filing is decoupled from the reopen mechanism, why
    this isn't folded into the original TDX quote). Additive and immutable
    once filed: nothing in this module or elsewhere mutates a Dispute after
    file_dispute() constructs it.

    filed_by / dispute_type / referenced_field are plain str (not the
    Literal types schemas.py defines for the API boundary) — same
    dataclass-layer convention as RoundEntry.actor/move above; validation
    happens in app.offercheck.disputes.file_dispute(), not at this layer.
    """
    dispute_id: str
    session_id: str
    filed_by: str  # "candidate" | "employer"
    dispute_type: str  # "process" | "outcome"
    evidence: str
    referenced_field: str | None  # "final_gap_pct" | "market_percentile" for outcome disputes; None for process disputes
    filed_at: str  # ISO-8601 UTC
    dispute_hash: str  # SHA-256 over the fields above (sorted-keys JSON) — tamper-evident, not itself part of the original TDX report_data
    # Lightweight status lifecycle (see app.offercheck.disputes.update_dispute_status) — plain str,
    # not a Literal, same dataclass-layer convention as filed_by/dispute_type above; validated in
    # disputes.py, not here. Mutated in place by update_dispute_status() — the one exception to this
    # dataclass otherwise being immutable once filed (dispute_hash is NOT recomputed on a status
    # change; it continues to seal only the original filing fields above, not these three).
    status: str = "OPEN"  # "OPEN" | "UNDER_REVIEW" | "RESOLVED" | "DISMISSED"
    resolution_note: str | None = None  # optional free text set on a transition; capped at disputes.EVIDENCE_MAX_LENGTH
    resolved_at: str | None = None  # ISO-8601 UTC — set only when status becomes RESOLVED or DISMISSED, never cleared


@dataclass
class Session:
    id: str
    candidate_token: str
    employer_token: str
    competing_offer: CompetingOffer
    consistency: ConsistencyCheck
    candidate_ask: float
    original_candidate_ask: float
    state: str = "PENDING_EMPLOYER"
    round_number: int = 0
    max_rounds: int = MAX_ROUNDS
    band_min: float | None = None
    band_mid: float | None = None
    band_max: float | None = None
    band_set: bool = False
    employer_current_offer: float | None = None
    opening_employer_offer: float | None = None  # employer's first-ever counter value, snapshotted once — see negotiation.final_gap_pct
    agreed_price: float | None = None
    market_percentile: float | None = None  # computed once at AGREED (routes.py::_maybe_attest) — see negotiation.market_percentile; requires an async fetch, so unlike final_gap_pct it can't be recomputed live on every read
    history: list[RoundEntry] = field(default_factory=list)
    attestation: str | None = None
    credential: OfferVerifiedCredential | None = None
    company_id: str | None = None  # Phase 3: set when created via company API key or an ATS webhook
    # Payment gating (see app.offercheck.credits) — Phase 4. Set (and re-checked) by
    # routes.py::_maybe_attest whenever a terminal session couldn't be billed (no company
    # attached yet, or the attached company is out of credit). False once attestation
    # actually happens — see that function's own docstring for the retry-safe contract.
    payment_required: bool = False
    ats_candidate_ref: str | None = None  # Phase 3: candidate/opportunity id in the company's ATS, for notify_outcome
    notified: bool = False  # Phase 3: billing/ATS side effects fired at most once per session
    # Phase 2A agentic negotiation (offercheck_phase2_spec.md) — sealed, never exposed via any response schema.
    candidate_floor: float | None = None
    candidate_priorities: str | None = None
    employer_authority_limit: float | None = None
    employer_priorities: str | None = None
    agentic_mode: bool = False
    agentic_mode_started_round: int | None = None  # first round_number decided by an agent — see mediator.py
    # Phase 2B full compensation package negotiation — sealed, never exposed via any response schema.
    # Parallel state, not reused scalar fields — see app.offercheck.package's module docstring for why.
    candidate_package_ask: dict | None = None
    candidate_total_comp_floor: float | None = None
    candidate_package_priorities: str | None = None
    employer_total_comp_budget: float | None = None
    package_state: str = "PENDING_EMPLOYER"
    package_round_number: int = 0
    candidate_current_package: dict | None = None
    employer_current_package: dict | None = None
    package_history: list[dict] = field(default_factory=list)
    package_agreed: dict | None = None
    package_attestation: str | None = None
    package_credential: PackageCredential | None = None
    package_notified: bool = False
    # Approval stage (see app.offercheck.negotiation's module docstring) — an "accept" lands
    # on PENDING_APPROVAL, not directly on AGREED. Each party casts exactly one vote here;
    # cleared back to None whenever the session reopens for another round of extension.
    candidate_approval_vote: str | None = None  # "approve" | "request_more_rounds" | "decline"
    employer_approval_vote: str | None = None
    extension_count: int = 0
    approval_history: list[dict] = field(default_factory=list)  # [{cycle, actor, decision}] — separate from RoundEntry/Move, never mixed into the negotiation history
    # Package-mode mirror of the same approval stage.
    candidate_package_approval_vote: str | None = None
    employer_package_approval_vote: str | None = None
    package_extension_count: int = 0
    package_approval_history: list[dict] = field(default_factory=list)
    # Provenance credential (see app.offercheck.provenance) — an optional, candidate-initiated,
    # on-demand proof of real git-commit history behind their claimed experience. Set only via
    # POST .../candidate/verify-credential; require_provenance_credential is an employer-set
    # policy flag (currently invite-flow only, see EmployerInviteRequest) enforced as a gate in
    # negotiation.apply_move(). Neither raw github_token nor repo/company names are ever stored
    # here — see app.offercheck.provenance's module docstring for the privacy discipline this
    # mirrors from app.devcred's SeniorDevCredential schema.
    require_provenance_credential: bool = False
    candidate_provenance_credential: dict | None = None
    # Dispute/contest surface (see app.offercheck.disputes) — additive, list-like: zero or more
    # disputes, from either party, potentially of both types (process | outcome). Filing never
    # mutates session.state or any already-attested field above; see that module's docstring for
    # why this is deliberately decoupled from the approval-vote reopen mechanism.
    disputes: list[Dispute] = field(default_factory=list)


_SESSIONS: dict[str, Session] = {}


def reset() -> None:
    """Test-only: clear all sessions between test cases."""
    _SESSIONS.clear()


def create_session(
    competing_offer: CompetingOffer,
    candidate_ask: float,
    consistency: ConsistencyCheck,
    company_id: str | None = None,
    ats_candidate_ref: str | None = None,
    candidate_floor: float | None = None,
    candidate_priorities: str | None = None,
    candidate_package_ask: dict | None = None,
    candidate_total_comp_floor: float | None = None,
    candidate_package_priorities: str | None = None,
) -> Session:
    session = Session(
        id=secrets.token_urlsafe(12),
        candidate_token=secrets.token_urlsafe(16),
        employer_token=secrets.token_urlsafe(16),
        competing_offer=competing_offer,
        consistency=consistency,
        candidate_ask=candidate_ask,
        original_candidate_ask=candidate_ask,
        company_id=company_id,
        ats_candidate_ref=ats_candidate_ref,
        candidate_floor=candidate_floor,
        candidate_priorities=candidate_priorities,
        candidate_package_ask=candidate_package_ask,
        candidate_total_comp_floor=candidate_total_comp_floor,
        candidate_package_priorities=candidate_package_priorities,
        candidate_current_package=candidate_package_ask,
    )
    _SESSIONS[session.id] = session
    return session


def get_session(session_id: str) -> Session | None:
    return _SESSIONS.get(session_id)


def all_sessions() -> list[Session]:
    """Every session currently held in memory — used by app.offercheck.export's
    admin-only training-data export route. Nothing else in this codebase needs to
    enumerate every session at once, so this stays a narrow, deliberate addition
    rather than exposing the underlying dict."""
    return list(_SESSIONS.values())
