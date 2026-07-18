"""
Offer Check routes — /api/offercheck/*.

Phase 1: no DB, no auth beyond opaque per-party tokens.
Phase 2 adds TDX attestation on session close and PDF offer-letter parsing.
Phase 3 adds company auth (API keys), bulk verification, a πCreds-style
conduct credential folded into the same attestation, ATS webhook receivers,
and billing usage tracking (see build_spec_offer_check.md).

Endpoints:
  POST /sessions                          candidate submits competing offer + ask (optional X-API-Key to tag a company)
  POST /employer/new                      authenticated employer opens an invite before any candidate exists (X-API-Key)
  GET  /employer/invite/{id}               invite status check, employer_token once claimed (X-API-Key, owning company only)
  POST /candidate/join/{id}                candidate claims an invite -> creates the Session (mirrors POST /sessions)
  POST /parse-offer-letter                candidate uploads a PDF -> draft fields to review
  POST /sessions/{id}/employer/band       employer's one-time private band -> gap preview
  POST /sessions/{id}/employer/move       employer accepts / counters / walks
  POST /sessions/{id}/candidate/move      candidate accepts / counters / walks
  POST /sessions/{id}/candidate/verify-credential  candidate proves git-commit provenance (app.offercheck.provenance); required before any candidate/move call iff the session has require_provenance_credential set
  POST /sessions/{id}/candidate/approval          vote at the PENDING_APPROVAL checkpoint: approve | request_more_rounds | decline
  POST /sessions/{id}/employer/approval           employer's counterpart to the above
  POST /sessions/{id}/candidate/approval-package  package-mode counterpart (package_state == PENDING_APPROVAL)
  POST /sessions/{id}/employer/approval-package   employer's counterpart to the above
  PATCH /sessions/{id}/candidate/enable-agentic  seal candidate_floor any time pre-terminal (not just at creation)
  PATCH /sessions/{id}/employer/enable-agentic   seal employer_authority_limit any time pre-terminal (after band is set)
  GET  /sessions/{id}                     viewer-scoped status poll (?token=...)
  GET  /sessions/{id}/attest              TDX attestation receipt (terminal states only)
  GET  /sessions/{id}/dcap-verify         parsed DCAP quote fields for the receipt above
  GET  /sessions/{id}/credential          πCreds-style conduct credential (token or X-API-Key)
  POST /company/register                  company signs up, gets an API key (shown once)
  POST /company/ats-connect               attach a Greenhouse/Lever/Workday API key (X-API-Key)
  POST /company/verify/bulk               create up to 50 sessions in one call (X-API-Key)
  GET  /company/sessions                  list this company's sessions (X-API-Key)
  POST /integrations/{provider}/webhook/{company_id}   inbound ATS webhook, HMAC-verified
  POST /sessions/{id}/start-agentic       run CandidateAgent vs EmployerAgent to completion (Phase 2A)
  POST /sessions/{id}/start-agentic-package  run full compensation package negotiation (Phase 2B)
  POST /auth/demo-link                    mint a magic-link demo token for a session (X-Internal-Key)
  GET  /auth/verify                       check a magic-link token's validity

Token identifies the caller as candidate or employer; it is never trusted to
also declare which party it is. Cross-party raw numbers never appear in a
response — only gap_pct, state, round history (moves only), and the
viewer's own current value. Company auth (Phase 3) sits alongside this, not
in place of it — see CLAUDE.md "Offer Check Architecture".

Magic-link auth (see app.offercheck.demo_auth): every Claude-calling
endpoint — currently only start-agentic — requires either a valid party
token OR a valid X-Demo-Token. No exceptions; any future agent-calling
endpoint must add the same check.
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile

from app.config import settings
from app.offercheck import auth, billing, credential, demo_auth, invites, negotiation, package, parsing, provenance, rate_limit, store, verifier
from app.offercheck.agents import mediator, package_mediator
from app.offercheck.integrations import greenhouse, lever, workday
from app.offercheck.integrations._shared import AtsNotConfigured
from app.offercheck.schemas import (
    AgenticResult,
    AgenticRoundDetail,
    AgenticStartRequest,
    ApprovalVoteRequest,
    AtsConnectRequest,
    AtsConnectResponse,
    AtsProvider,
    AttestationReceipt,
    BulkVerifyRequest,
    BulkVerifyResponse,
    BulkVerifyResult,
    CandidateEnableAgenticRequest,
    CandidateEnablePackageAgenticRequest,
    CandidateJoinRequest,
    CandidateSubmitRequest,
    CandidateSubmitResponse,
    CompanyRegisterRequest,
    CompanyRegisterResponse,
    CompanySessionSummary,
    CompanySessionsResponse,
    CredentialResponse,
    DcapVerification,
    DemoLinkRequest,
    DemoLinkResponse,
    EmployerBandRequest,
    EmployerBandResponse,
    EmployerEnableAgenticRequest,
    EmployerEnablePackageAgenticRequest,
    EmployerInviteRequest,
    EmployerInviteResponse,
    ExtractedOfferFields,
    InviteStatusResponse,
    MoveRequest,
    OfferLetterExtraction,
    OfferPackage,
    PackageAgenticResult,
    PackageCredentialResponse,
    PackageRoundDetail,
    ProvenanceCredentialSummary,
    RoundSummary,
    SessionView,
    VerifyCredentialRequest,
    VerifyCredentialResponse,
    VerifyTokenResponse,
)
from app.offercheck.store import Session
from app.tee.attestation import sign_result
from app.tee.dcap import parse_tdx_quote

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/offercheck", tags=["offercheck"])

_ATS_INTEGRATIONS = {"greenhouse": greenhouse, "lever": lever, "workday": workday}


def _get_session_or_404(session_id: str) -> Session:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


def _resolve_viewer(session: Session, token: str) -> str:
    if token == session.candidate_token:
        return "candidate"
    if token == session.employer_token:
        return "employer"
    raise HTTPException(status_code=403, detail="invalid token for this session")


def _require_company(x_api_key: str | None) -> auth.Company:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    company = auth.get_company_by_api_key(x_api_key)
    if company is None:
        raise HTTPException(status_code=403, detail="invalid API key")
    return company


def _view_for(session: Session, viewer: str) -> SessionView:
    my_value = session.candidate_ask if viewer == "candidate" else session.employer_current_offer
    return SessionView(
        session_id=session.id,
        state=session.state,
        round_number=session.round_number,
        max_rounds=session.max_rounds,
        turn=negotiation.current_turn(session),
        band_set=session.band_set,
        gap_pct=negotiation.live_gap_pct(session),
        history=[
            RoundSummary(
                round_number=r.round_number,
                actor=r.actor,
                move=r.move,
                # Only exposed for rounds actually decided by an agent (round_number >=
                # agentic_mode_started_round) — that's the moment the offer amount legitimately
                # crosses the agent boundary (see mediator.py). A round decided by a human, even
                # in a session that later switches to agentic mode, was made under the
                # non-negotiable gap%-only privacy contract and must stay that way — it doesn't
                # retroactively become visible just because agentic mode starts later.
                value=(
                    r.value
                    if session.agentic_mode and session.agentic_mode_started_round is not None
                    and r.round_number >= session.agentic_mode_started_round
                    else None
                ),
            )
            for r in session.history
        ],
        consistency=session.consistency,
        agreed_price=session.agreed_price,
        my_current_value=my_value,
        agentic_ready=session.candidate_floor is not None and session.employer_authority_limit is not None,
        my_agentic_sealed=(
            session.candidate_floor is not None if viewer == "candidate" else session.employer_authority_limit is not None
        ),
        other_agentic_sealed=(
            session.employer_authority_limit is not None if viewer == "candidate" else session.candidate_floor is not None
        ),
        my_approval_vote=(
            session.candidate_approval_vote if viewer == "candidate" else session.employer_approval_vote
        ),
        other_approval_vote=(
            session.employer_approval_vote if viewer == "candidate" else session.candidate_approval_vote
        ),
        extension_count=session.extension_count,
        package_agentic_ready=(
            session.candidate_package_ask is not None
            and session.candidate_total_comp_floor is not None
            and session.band_set
            and session.employer_total_comp_budget is not None
        ),
        package_state=session.package_state,
        package_round_number=session.package_round_number,
        package_turn=package.package_current_turn(session),
        package_history=[
            PackageRoundDetail(
                round=r["round"],
                actor=r["actor"],
                move=r["move"],
                package=OfferPackage(**r["package"]) if r.get("package") else None,
                total_comp=package.total_comp_value(r["package"]) if r.get("package") else None,
            )
            for r in session.package_history
        ],
        package_agreed_package=OfferPackage(**session.package_agreed) if session.package_agreed else None,
        my_package_agentic_sealed=(
            session.candidate_total_comp_floor is not None
            if viewer == "candidate"
            else session.employer_total_comp_budget is not None
        ),
        other_package_agentic_sealed=(
            session.employer_total_comp_budget is not None
            if viewer == "candidate"
            else session.candidate_total_comp_floor is not None
        ),
        my_package_approval_vote=(
            session.candidate_package_approval_vote if viewer == "candidate" else session.employer_package_approval_vote
        ),
        other_package_approval_vote=(
            session.employer_package_approval_vote if viewer == "candidate" else session.candidate_package_approval_vote
        ),
        package_extension_count=session.package_extension_count,
        package_converged_hint=(
            session.candidate_current_package is not None
            and session.employer_current_package is not None
            and package.is_converged(
                package.total_comp_value(session.candidate_current_package),
                package.total_comp_value(session.employer_current_package),
            )
        ),
        require_provenance_credential=session.require_provenance_credential,
        candidate_provenance_verified=session.candidate_provenance_credential is not None,
        candidate_provenance_credential=(
            ProvenanceCredentialSummary(**session.candidate_provenance_credential)
            if session.candidate_provenance_credential
            else None
        ),
    )


def _credential_response(session: Session) -> CredentialResponse | None:
    if session.credential is None:
        return None
    c = session.credential
    return CredentialResponse(
        session_id=c.session_id,
        genuine_negotiation=c.genuine_negotiation,
        round_count=c.round_count,
        outcome=c.outcome,
        issues=c.issues,
        summary=c.summary,
        credential_hash=c.credential_hash,
        tee_attested=settings.tee_mode == "production",
    )


def _handle_negotiation_error(exc: negotiation.OfferCheckError) -> None:
    if isinstance(exc, negotiation.WrongTurn):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (negotiation.SessionTerminal, negotiation.BandAlreadySet, negotiation.AlreadyVoted)):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, negotiation.BandNotSet):
        raise HTTPException(status_code=412, detail=str(exc))
    if isinstance(exc, negotiation.NotPendingApproval):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, negotiation.ProvenanceCredentialRequired):
        raise HTTPException(status_code=412, detail=str(exc))
    raise HTTPException(status_code=400, detail=str(exc))


async def _maybe_attest(session: Session) -> None:
    """
    Once a session reaches a terminal state, compute the conduct credential
    and produce a TDX quote binding the outcome + credential hash + hashes of
    the private inputs. Runs at most once per session — idempotent so callers
    don't need to track whether attestation already ran.
    """
    if session.state not in negotiation.TERMINAL_STATES or session.attestation is not None:
        return
    session.credential = credential.compute_credential(session)
    terms = negotiation.attested_terms(session, credential_hash=session.credential.credential_hash)
    session.attestation = await sign_result(terms)


async def _maybe_notify(session: Session) -> None:
    """
    Phase 3 side effects once a session closes: billing usage + an ATS
    outcome note, both non-fatal. Runs at most once per session.
    """
    if session.attestation is None or session.notified or session.company_id is None:
        return
    session.notified = True

    company = auth.get_company(session.company_id)
    if company is None:
        return

    try:
        await billing.record_verification_usage(company.id, company.plan)
    except billing.StripeNotConfigured:
        logger.info(f"session {session.id}: billing not configured, skipping usage record")
    except Exception as exc:
        logger.warning(f"session {session.id}: billing usage record failed — {exc}")

    if company.ats_provider and session.ats_candidate_ref and session.credential:
        integration = _ATS_INTEGRATIONS.get(company.ats_provider)
        try:
            await integration.notify_outcome(company.ats_api_key, session.ats_candidate_ref, session.credential.summary)
        except AtsNotConfigured:
            logger.info(f"session {session.id}: {company.ats_provider} not connected, skipping ATS notify")
        except Exception as exc:
            logger.warning(f"session {session.id}: {company.ats_provider} notify failed — {exc}")


def _package_credential_response(session: Session) -> PackageCredentialResponse | None:
    if session.package_credential is None:
        return None
    c = session.package_credential
    return PackageCredentialResponse(
        session_id=c.session_id,
        genuine_negotiation=c.genuine_negotiation,
        round_count=c.round_count,
        outcome=c.outcome,
        issues=c.issues,
        summary=c.summary,
        credential_hash=c.credential_hash,
        tee_attested=settings.tee_mode == "production",
    )


async def _maybe_attest_package(session: Session) -> None:
    """Phase 2B counterpart to _maybe_attest() — same idempotency guard, same
    credential-hash-folded-into-the-quote pattern, over package_state instead of state."""
    if session.package_state not in package.PACKAGE_TERMINAL_STATES or session.package_attestation is not None:
        return
    session.package_credential = credential.compute_package_credential(session)
    terms = package.attested_package_terms(session, credential_hash=session.package_credential.credential_hash)
    session.package_attestation = await sign_result(terms)


async def _maybe_notify_package(session: Session) -> None:
    """Phase 3B counterpart to _maybe_notify() — same non-fatal billing/ATS side effects."""
    if session.package_attestation is None or session.package_notified or session.company_id is None:
        return
    session.package_notified = True

    company = auth.get_company(session.company_id)
    if company is None:
        return

    try:
        await billing.record_verification_usage(company.id, company.plan)
    except billing.StripeNotConfigured:
        logger.info(f"session {session.id}: billing not configured, skipping package usage record")
    except Exception as exc:
        logger.warning(f"session {session.id}: package billing usage record failed — {exc}")

    if company.ats_provider and session.ats_candidate_ref and session.package_credential:
        integration = _ATS_INTEGRATIONS.get(company.ats_provider)
        try:
            await integration.notify_outcome(company.ats_api_key, session.ats_candidate_ref, session.package_credential.summary)
        except AtsNotConfigured:
            logger.info(f"session {session.id}: {company.ats_provider} not connected, skipping package ATS notify")
        except Exception as exc:
            logger.warning(f"session {session.id}: {company.ats_provider} package notify failed — {exc}")


@router.post("/sessions", response_model=CandidateSubmitResponse)
async def submit_session(
    body: CandidateSubmitRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> CandidateSubmitResponse:
    rate_limit.check_session_create(request)

    company = None
    if x_api_key is not None:
        company = _require_company(x_api_key)

    consistency = verifier.check_consistency(body.competing_offer, body.candidate_ask)
    session = store.create_session(
        body.competing_offer,
        body.candidate_ask,
        consistency,
        company_id=company.id if company else None,
        ats_candidate_ref=body.ats_candidate_ref,
        candidate_floor=body.candidate_floor,
        candidate_priorities=body.candidate_priorities,
        candidate_package_ask=body.candidate_package_ask.model_dump() if body.candidate_package_ask else None,
        candidate_total_comp_floor=body.candidate_total_comp_floor,
        candidate_package_priorities=body.candidate_package_priorities,
    )
    if company is not None:
        auth.record_session(company, session.id)

    return CandidateSubmitResponse(
        session_id=session.id,
        candidate_token=session.candidate_token,
        employer_token=session.employer_token,
        employer_link=f"/offercheck/employer/{session.id}?token={session.employer_token}",
        state=session.state,
        consistency=consistency,
    )


@router.post("/employer/new", response_model=EmployerInviteResponse, status_code=201)
async def create_employer_invite_route(
    body: EmployerInviteRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> EmployerInviteResponse:
    """
    Employer-initiated counterpart to POST /sessions (candidate-initiated).
    An authenticated company opens a negotiation before any candidate exists
    — no Session, no tokens, until a candidate claims the invite at
    POST /candidate/join/{invite_id}.
    """
    company = _require_company(x_api_key)
    invite = invites.create_invite(
        company.id,
        body.band_min,
        body.band_mid,
        body.band_max,
        requirements=body.requirements,
        ats_candidate_ref=body.ats_candidate_ref,
        employer_authority_limit=body.employer_authority_limit,
        employer_priorities=body.employer_priorities,
        require_provenance_credential=body.require_provenance_credential,
    )
    return EmployerInviteResponse(
        invite_id=invite.id,
        candidate_join_link=f"/offercheck/candidate/join/{invite.id}",
        status=invite.status,
    )


@router.get("/employer/invite/{invite_id}", response_model=InviteStatusResponse)
async def get_employer_invite_route(
    invite_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> InviteStatusResponse:
    """
    Status check for the invite's own creating company. Gated by X-API-Key
    (not just invite_id) because, once claimed, this hands back the
    employer_token needed to act on the resulting session — the same
    information POST /sessions gives the candidate directly, just deferred
    here until a candidate exists to negotiate with.
    """
    company = _require_company(x_api_key)
    invite = invites.get_invite(invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="invite not found")
    if invite.company_id != company.id:
        raise HTTPException(status_code=403, detail="invite does not belong to this company")

    employer_token = None
    if invite.status == invites.CLAIMED and invite.session_id:
        session = store.get_session(invite.session_id)
        employer_token = session.employer_token if session else None

    return InviteStatusResponse(
        invite_id=invite.id,
        status=invite.status,
        session_id=invite.session_id,
        employer_token=employer_token,
    )


@router.post("/candidate/join/{invite_id}", response_model=CandidateSubmitResponse)
async def join_invite_route(invite_id: str, body: CandidateJoinRequest, request: Request) -> CandidateSubmitResponse:
    """
    Candidate-side claim of an employer-initiated invite. The one place
    store.create_session() runs for this flow — identical call shape to
    POST /sessions, just sourcing company_id/ats_candidate_ref/employer_*
    fields from the invite instead of an X-API-Key header. Immediately seals
    the employer's band from the invite via the existing
    negotiation.set_employer_band(), so the resulting session lands exactly
    where it would have had the employer called POST .../employer/band by
    hand — same state machine, same turn order, nothing new.
    """
    rate_limit.check_session_create(request)
    invite = invites.get_invite(invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="invite not found")
    if invite.status == invites.CLAIMED:
        raise HTTPException(status_code=409, detail="invite has already been claimed")

    consistency = verifier.check_consistency(body.competing_offer, body.candidate_ask)
    session = store.create_session(
        body.competing_offer,
        body.candidate_ask,
        consistency,
        company_id=invite.company_id,
        ats_candidate_ref=invite.ats_candidate_ref,
        candidate_floor=body.candidate_floor,
        candidate_priorities=body.candidate_priorities,
    )
    negotiation.set_employer_band(session, invite.band_min, invite.band_mid, invite.band_max)
    session.employer_authority_limit = invite.employer_authority_limit
    session.employer_priorities = invite.employer_priorities
    session.require_provenance_credential = invite.require_provenance_credential

    invites.claim_invite(invite, session.id)

    company = auth.get_company(invite.company_id)
    if company is not None:
        auth.record_session(company, session.id)

    return CandidateSubmitResponse(
        session_id=session.id,
        candidate_token=session.candidate_token,
        employer_token=session.employer_token,
        employer_link=f"/offercheck/employer/{session.id}?token={session.employer_token}",
        state=session.state,
        consistency=consistency,
    )


@router.post("/parse-offer-letter", response_model=OfferLetterExtraction)
async def parse_offer_letter_route(file: UploadFile = File(...)) -> OfferLetterExtraction:
    """
    Best-effort PDF -> draft field extraction. Never persisted, never bound to
    a session — the candidate reviews/corrects the result client-side, then
    POSTs the (possibly edited) fields to /sessions like any other submission.
    """
    pdf_bytes = await file.read()
    try:
        data = await parsing.parse_offer_letter(pdf_bytes)
    except parsing.OfferLetterParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return OfferLetterExtraction(
        competing_offer=ExtractedOfferFields(
            company=data.get("company") or "",
            role=data.get("role") or "",
            base_salary=data.get("base_salary") or 0,
            equity_value=data.get("equity_value") or 0,
            bonus=data.get("bonus") or 0,
            start_date=data.get("start_date") or "",
        ),
        confidence=data.get("confidence") or "low",
        notes=data.get("notes") or [],
    )


@router.post("/sessions/{session_id}/employer/band", response_model=EmployerBandResponse)
async def submit_employer_band(session_id: str, body: EmployerBandRequest) -> EmployerBandResponse:
    session = _get_session_or_404(session_id)
    if body.employer_token != session.employer_token:
        raise HTTPException(status_code=403, detail="invalid employer token")
    try:
        gap = negotiation.set_employer_band(session, body.band_min, body.band_mid, body.band_max)
    except negotiation.OfferCheckError as exc:
        _handle_negotiation_error(exc)
    session.employer_authority_limit = body.employer_authority_limit
    session.employer_priorities = body.employer_priorities
    session.employer_total_comp_budget = body.employer_total_comp_budget
    return EmployerBandResponse(session_id=session.id, state=session.state, band_set=session.band_set, gap_pct=gap)


@router.post("/sessions/{session_id}/employer/move", response_model=SessionView)
async def employer_move(session_id: str, body: MoveRequest) -> SessionView:
    session = _get_session_or_404(session_id)
    if body.token != session.employer_token:
        raise HTTPException(status_code=403, detail="invalid employer token")
    try:
        negotiation.apply_move(session, actor="employer", move=body.move, value=body.value)
    except negotiation.OfferCheckError as exc:
        _handle_negotiation_error(exc)
    await _maybe_attest(session)
    await _maybe_notify(session)
    return _view_for(session, "employer")


@router.post("/sessions/{session_id}/candidate/move", response_model=SessionView)
async def candidate_move(session_id: str, body: MoveRequest) -> SessionView:
    session = _get_session_or_404(session_id)
    if body.token != session.candidate_token:
        raise HTTPException(status_code=403, detail="invalid candidate token")
    try:
        negotiation.apply_move(session, actor="candidate", move=body.move, value=body.value)
    except negotiation.OfferCheckError as exc:
        _handle_negotiation_error(exc)
    await _maybe_attest(session)
    await _maybe_notify(session)
    return _view_for(session, "candidate")


@router.post("/sessions/{session_id}/candidate/verify-credential", response_model=VerifyCredentialResponse)
async def verify_credential_route(session_id: str, body: VerifyCredentialRequest, request: Request) -> VerifyCredentialResponse:
    """
    Candidate-initiated, on-demand proof of real git-commit history behind their
    claimed experience — see app.offercheck.provenance for the full two-layer
    pipeline (deterministic GitInspectorAgent + LLM GitEvaluatorAgent, same as
    app.devcred's own product). Rate-limited tighter than a plain GitHub-fetch
    endpoint because it makes a paid Claude call — see rate_limit.check_provenance_verify.

    Not gated by session state or turn order — a candidate may verify before,
    during, or after the employer sets require_provenance_credential; only
    negotiation.apply_move()'s gate enforces the requirement, at the moment it
    actually matters. github_token is used in-memory only for this one call and
    never persisted, same discipline as app.devcred.routes.ingest_repos.
    """
    rate_limit.check_provenance_verify(request)
    session = _get_session_or_404(session_id)
    if body.token != session.candidate_token:
        raise HTTPException(status_code=403, detail="invalid candidate token")

    for repo in body.repos:
        if "/" not in repo or repo.startswith("/") or repo.endswith("/"):
            raise HTTPException(status_code=400, detail=f"Invalid repo format (expected owner/repo): {repo}")

    summary = await provenance.verify_git_provenance(body.github_token, body.repos)
    session.candidate_provenance_credential = summary

    return VerifyCredentialResponse(session_id=session.id, credential=ProvenanceCredentialSummary(**summary))


@router.post("/sessions/{session_id}/employer/approval", response_model=SessionView)
async def employer_approval(session_id: str, body: ApprovalVoteRequest) -> SessionView:
    """
    Employer's vote at the PENDING_APPROVAL checkpoint (see
    app.offercheck.negotiation's module docstring for the resolution rule).
    This is the ONE human touchpoint per negotiation cycle — even for a
    fully agentic session, run_agentic_negotiation() stops at
    PENDING_APPROVAL and returns without attesting; only this endpoint (and
    its candidate counterpart) can move the session past it. Attestation
    fires here, not in start-agentic, once the vote resolves to AGREED.
    """
    session = _get_session_or_404(session_id)
    if body.token != session.employer_token:
        raise HTTPException(status_code=403, detail="invalid employer token")
    try:
        negotiation.apply_approval_vote(session, actor="employer", decision=body.decision)
    except negotiation.OfferCheckError as exc:
        _handle_negotiation_error(exc)
    await _maybe_attest(session)
    await _maybe_notify(session)
    return _view_for(session, "employer")


@router.post("/sessions/{session_id}/candidate/approval", response_model=SessionView)
async def candidate_approval(session_id: str, body: ApprovalVoteRequest) -> SessionView:
    """Candidate's counterpart to employer_approval — see that docstring."""
    session = _get_session_or_404(session_id)
    if body.token != session.candidate_token:
        raise HTTPException(status_code=403, detail="invalid candidate token")
    try:
        negotiation.apply_approval_vote(session, actor="candidate", decision=body.decision)
    except negotiation.OfferCheckError as exc:
        _handle_negotiation_error(exc)
    await _maybe_attest(session)
    await _maybe_notify(session)
    return _view_for(session, "candidate")


@router.post("/sessions/{session_id}/employer/approval-package", response_model=SessionView)
async def employer_approval_package(session_id: str, body: ApprovalVoteRequest) -> SessionView:
    """
    Package-mode counterpart to employer_approval — package negotiation's
    first-ever human touchpoint (it was agentic-only before this stage
    existed; deliberate, for consistency with the scalar flow, not an
    accident). run_package_negotiation() stops at package_state ==
    PENDING_APPROVAL the same way the scalar mediator does.
    """
    session = _get_session_or_404(session_id)
    if body.token != session.employer_token:
        raise HTTPException(status_code=403, detail="invalid employer token")
    try:
        package.apply_package_approval_vote(session, actor="employer", decision=body.decision)
    except (package.PackageNotPendingApproval, package.PackageAlreadyVoted) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await _maybe_attest_package(session)
    await _maybe_notify_package(session)
    return _view_for(session, "employer")


@router.post("/sessions/{session_id}/candidate/approval-package", response_model=SessionView)
async def candidate_approval_package(session_id: str, body: ApprovalVoteRequest) -> SessionView:
    """Candidate's counterpart to employer_approval_package — see that docstring."""
    session = _get_session_or_404(session_id)
    if body.token != session.candidate_token:
        raise HTTPException(status_code=403, detail="invalid candidate token")
    try:
        package.apply_package_approval_vote(session, actor="candidate", decision=body.decision)
    except (package.PackageNotPendingApproval, package.PackageAlreadyVoted) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await _maybe_attest_package(session)
    await _maybe_notify_package(session)
    return _view_for(session, "candidate")


@router.patch("/sessions/{session_id}/candidate/enable-agentic", response_model=SessionView)
async def enable_candidate_agentic(session_id: str, body: CandidateEnableAgenticRequest) -> SessionView:
    """
    Seals candidate_floor any time before the session is terminal — not just
    at the one-shot POST /sessions moment. Added because the original
    creation-time-only checkbox meant a candidate who forgot to opt in (or
    decided partway through a human negotiation that they want AI to take
    over) had no way to enable it after the fact. Single-set, same as the
    original creation-time field: once sealed it can't be silently changed,
    matching CandidateSubmitRequest.candidate_floor's "sealed" contract.
    """
    session = _get_session_or_404(session_id)
    if body.token != session.candidate_token:
        raise HTTPException(status_code=403, detail="invalid candidate token")
    if session.state in negotiation.TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="session is already terminal")
    if session.candidate_floor is not None:
        raise HTTPException(status_code=409, detail="candidate has already sealed a floor for this session")
    session.candidate_floor = body.candidate_floor
    session.candidate_priorities = body.candidate_priorities
    return _view_for(session, "candidate")


@router.patch("/sessions/{session_id}/employer/enable-agentic", response_model=SessionView)
async def enable_employer_agentic(session_id: str, body: EmployerEnableAgenticRequest) -> SessionView:
    """Employer counterpart to enable_candidate_agentic — see that docstring. Requires the band
    to already be set (employer_authority_limit is meaningless without band_max to clamp against,
    same precondition mediator.build_agents() already enforces at start-agentic time)."""
    session = _get_session_or_404(session_id)
    if body.token != session.employer_token:
        raise HTTPException(status_code=403, detail="invalid employer token")
    if session.state in negotiation.TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="session is already terminal")
    if not session.band_set:
        raise HTTPException(status_code=412, detail="employer must submit their salary band first")
    if session.employer_authority_limit is not None:
        raise HTTPException(status_code=409, detail="employer has already sealed an authority limit for this session")
    session.employer_authority_limit = body.employer_authority_limit
    session.employer_priorities = body.employer_priorities
    return _view_for(session, "employer")


_DEFAULT_PACKAGE_TERMS = {
    "equity_grant": 0.0, "vesting_years": 4.0, "cliff_months": 12.0, "signing_bonus": 0.0,
    "annual_bonus_pct": 0.0, "remote": "hybrid", "start_date_days": 30.0, "pto_days": 15.0,
}


@router.patch("/sessions/{session_id}/candidate/enable-agentic-package", response_model=SessionView)
async def enable_candidate_package_agentic(session_id: str, body: CandidateEnablePackageAgenticRequest) -> SessionView:
    """
    Package-mode counterpart to enable_candidate_agentic. The UI only asks for one number
    (candidate_total_comp_floor) — candidate_package_ask (the full opening package
    PackageCandidateAgent needs) is synthesized here from session.candidate_ask as `base` plus
    neutral defaults (_DEFAULT_PACKAGE_TERMS) for every other term, only if not already set by
    an earlier creation-time submission. Single-set otherwise, same "sealed" contract as the
    scalar version.
    """
    session = _get_session_or_404(session_id)
    if body.token != session.candidate_token:
        raise HTTPException(status_code=403, detail="invalid candidate token")
    if session.state in negotiation.TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="session is already terminal")
    if session.candidate_total_comp_floor is not None:
        raise HTTPException(status_code=409, detail="candidate has already sealed package agentic negotiation for this session")
    session.candidate_total_comp_floor = body.candidate_total_comp_floor
    session.candidate_package_priorities = body.candidate_package_priorities
    if session.candidate_package_ask is None:
        session.candidate_package_ask = {"base": session.candidate_ask, **_DEFAULT_PACKAGE_TERMS}
        session.candidate_current_package = session.candidate_package_ask
    return _view_for(session, "candidate")


@router.patch("/sessions/{session_id}/employer/enable-agentic-package", response_model=SessionView)
async def enable_employer_package_agentic(session_id: str, body: EmployerEnablePackageAgenticRequest) -> SessionView:
    """Package-mode counterpart to enable_employer_agentic — seals employer_total_comp_budget.
    No synthesis needed here: PackageEmployerAgent only ever needs band_min/mid/max (already set
    at band-submission time) plus this budget."""
    session = _get_session_or_404(session_id)
    if body.token != session.employer_token:
        raise HTTPException(status_code=403, detail="invalid employer token")
    if session.state in negotiation.TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="session is already terminal")
    if not session.band_set:
        raise HTTPException(status_code=412, detail="employer must submit their salary band first")
    if session.employer_total_comp_budget is not None:
        raise HTTPException(status_code=409, detail="employer has already sealed package agentic negotiation for this session")
    session.employer_total_comp_budget = body.employer_total_comp_budget
    session.employer_priorities = body.employer_priorities or session.employer_priorities
    return _view_for(session, "employer")


@router.get("/sessions/{session_id}", response_model=SessionView)
async def get_session_view(session_id: str, token: str) -> SessionView:
    session = _get_session_or_404(session_id)
    viewer = _resolve_viewer(session, token)
    return _view_for(session, viewer)


@router.get("/sessions/{session_id}/attest", response_model=AttestationReceipt)
async def get_attestation_receipt(session_id: str, token: str) -> AttestationReceipt:
    """
    TDX attestation receipt for a closed session. Either party's token works —
    the receipt itself contains nothing that isn't already known to both
    parties once the session is terminal (the outcome, plus hashes of the
    private inputs, never the raw inputs themselves).
    """
    session = _get_session_or_404(session_id)
    _resolve_viewer(session, token)
    if session.attestation is None:
        raise HTTPException(status_code=409, detail="attestation not available until the session closes")

    return AttestationReceipt(
        session_id=session.id,
        state=session.state,
        round_number=session.round_number,
        agreed_price=session.agreed_price,
        competing_offer_hash=negotiation.competing_offer_hash(session),
        employer_band_hash=negotiation.employer_band_hash(session),
        credential_hash=session.credential.credential_hash if session.credential else None,
        attestation=session.attestation,
        tee_attested=settings.tee_mode == "production",
        tee_mode=settings.tee_mode,
    )


@router.get("/sessions/{session_id}/dcap-verify", response_model=DcapVerification)
async def get_dcap_verification(session_id: str, token: str) -> DcapVerification:
    session = _get_session_or_404(session_id)
    _resolve_viewer(session, token)
    if session.attestation is None:
        raise HTTPException(status_code=409, detail="attestation not available until the session closes")

    parsed = parse_tdx_quote(session.attestation)
    return DcapVerification(session_id=session.id, **parsed)


@router.get("/sessions/{session_id}/credential", response_model=CredentialResponse)
async def get_credential_route(
    session_id: str,
    token: str | None = None,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> CredentialResponse:
    """
    πCreds-style conduct credential. Either the per-session token (candidate
    or employer) or the owning company's API key grants access — both prove
    you're a legitimate party to this specific session.
    """
    session = _get_session_or_404(session_id)
    if x_api_key is not None:
        company = auth.get_company_by_api_key(x_api_key)
        if company is None or company.id != session.company_id:
            raise HTTPException(status_code=403, detail="invalid API key for this session")
    elif token is not None:
        _resolve_viewer(session, token)
    else:
        raise HTTPException(status_code=401, detail="token or X-API-Key required")

    response = _credential_response(session)
    if response is None:
        raise HTTPException(status_code=409, detail="credential not available until the session closes")
    return response


@router.post("/company/register", response_model=CompanyRegisterResponse, status_code=201)
async def register_company_route(body: CompanyRegisterRequest) -> CompanyRegisterResponse:
    company, raw_key = auth.register_company(body.name)
    plan = billing.recommend_plan(body.hires_per_year)
    company.plan = plan
    return CompanyRegisterResponse(
        company_id=company.id,
        api_key=raw_key,
        recommended_plan=plan,
        pricing=billing.pricing_for_plan(plan),
    )


@router.post("/company/ats-connect", response_model=AtsConnectResponse)
async def connect_ats_route(
    body: AtsConnectRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AtsConnectResponse:
    company = _require_company(x_api_key)
    auth.connect_ats(company, body.provider, body.api_key)
    return AtsConnectResponse(company_id=company.id, provider=body.provider, connected=True)


@router.post("/company/verify/bulk", response_model=BulkVerifyResponse)
async def bulk_verify_route(
    body: BulkVerifyRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> BulkVerifyResponse:
    company = _require_company(x_api_key)
    results = []
    for item in body.verifications:
        consistency = verifier.check_consistency(item.competing_offer, item.candidate_ask)
        session = store.create_session(
            item.competing_offer,
            item.candidate_ask,
            consistency,
            company_id=company.id,
            ats_candidate_ref=item.ats_candidate_ref,
        )
        auth.record_session(company, session.id)
        results.append(
            BulkVerifyResult(
                session_id=session.id,
                candidate_token=session.candidate_token,
                employer_token=session.employer_token,
                employer_link=f"/offercheck/employer/{session.id}?token={session.employer_token}",
                consistency=consistency,
            )
        )
    return BulkVerifyResponse(company_id=company.id, results=results)


@router.get("/company/sessions", response_model=CompanySessionsResponse)
async def list_company_sessions_route(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> CompanySessionsResponse:
    company = _require_company(x_api_key)
    summaries = []
    for session_id in company.session_ids:
        session = store.get_session(session_id)
        if session is None:
            continue
        summaries.append(
            CompanySessionSummary(
                session_id=session.id,
                state=session.state,
                round_number=session.round_number,
                gap_pct=negotiation.live_gap_pct(session),
                employer_link=f"/offercheck/employer/{session.id}?token={session.employer_token}",
                ats_candidate_ref=session.ats_candidate_ref,
            )
        )
    return CompanySessionsResponse(company_id=company.id, sessions=summaries)


@router.post("/integrations/{provider}/webhook/{company_id}")
async def ats_webhook_route(
    provider: AtsProvider,
    company_id: str,
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
) -> dict:
    """
    Inbound ATS webhook receiver. Auth is entirely the HMAC signature — there
    is no API-key exchange in this direction, since the vendor is calling us.
    `company_id` in the path selects whose webhook_secret to verify against;
    it is not itself a credential (same trust model as session_id + token).
    """
    company = auth.get_company(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="unknown company")
    if company.ats_provider != provider:
        raise HTTPException(status_code=400, detail=f"company has not connected {provider}")

    integration = _ATS_INTEGRATIONS[provider]
    raw_body = await request.body()
    if not integration.verify_signature(raw_body, x_signature or "", company.webhook_secret):
        raise HTTPException(status_code=403, detail="invalid webhook signature")

    return {"received": True, "provider": provider}


def _authorize_agentic_call(session: Session, party_token: str | None, demo_token: str | None) -> None:
    """
    SECURITY RULE: start-agentic calls Claude — it must never run for an
    unauthenticated caller. Either proof is sufficient (not both required):
      (a) a valid party token — you're already an authenticated participant
          in this session, exactly as for every other session endpoint.
      (b) a valid, unexpired, unconsumed magic-link token (X-Demo-Token
          header or ?token= query param) — minted via POST /auth/demo-link
          for sharing with someone who isn't a party to the negotiation.
    (b) is single-use: consumed here, on successful validation, before the
    negotiation runs — not gated on the negotiation later succeeding.

    # TODO: replace with TinyCloud OpenKey delegation when available.
    """
    if party_token:
        try:
            _resolve_viewer(session, party_token)
            return
        except HTTPException:
            pass  # fall through to the demo-token check

    if demo_token:
        try:
            demo_auth.verify_token(session.id, demo_token)
        except demo_auth.InvalidToken as exc:
            raise HTTPException(status_code=401, detail=f"invalid demo token: {exc}")
        if demo_auth.is_consumed(demo_token):
            raise HTTPException(status_code=401, detail="demo token already used")
        demo_auth.consume(demo_token)
        return

    raise HTTPException(status_code=401, detail="a valid party token or demo token is required")


async def _parse_agentic_start_body(request: Request) -> AgenticStartRequest:
    """
    Manually parses + validates the request body for start-agentic(-package) instead of
    letting FastAPI auto-inject it as a `body: AgenticStartRequest` parameter.

    Why: a live 422 ("Input should be a valid dictionary or object to extract fields from")
    on these two endpoints specifically was reported repeatedly from the deployed app — the
    body Pydantic received was a JSON *string* (`'{"token":"..."}'`) instead of a parsed
    object. It never reproduced against this codebase in pytest, TestClient, or direct curl —
    only in the real browser-to-Phala round trip, which involves a CORS preflight and a
    dstack reverse proxy neither of those tools exercise. Rather than keep guessing at which
    hop in that chain re-wraps the body, parse it manually here and tolerate either shape:
    a normal dict, or a JSON string that itself decodes to the dict. This is strictly more
    permissive than FastAPI's default body injection, not a behavior change for any client
    that was already sending a correctly-encoded body.
    """
    raw = await request.body()
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="request body is not valid JSON")
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="request body is not valid JSON")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="request body must be a JSON object")
    return AgenticStartRequest.model_validate(parsed)


@router.post("/sessions/{session_id}/start-agentic", response_model=AgenticResult)
async def start_agentic_route(
    session_id: str,
    request: Request,
    x_demo_token: str | None = Header(default=None, alias="X-Demo-Token"),
    query_token: str | None = Query(default=None, alias="token"),
) -> AgenticResult:
    """
    Phase 2A (offercheck_phase2_spec.md): runs CandidateAgent vs EmployerAgent
    to completion over the same state machine a human would drive. Requires
    both sides to have already sealed their private inputs — candidate_floor
    at POST /sessions time, employer_authority_limit at POST .../employer/band
    time.

    Auth: see _authorize_agentic_call — a party token (body.token) OR a
    magic-link demo token (X-Demo-Token header, or ?token= query param for
    shareable URLs) is required. This call also counts against the
    per-session Claude-call spend cap (demo_auth.SPEND_CAP_PER_SESSION) and
    the per-IP rate limit (rate_limit.AGENTIC_CALL_LIMIT) — the spend cap
    alone isn't enough since it resets on a fresh session (see rate_limit.py).
    """
    rate_limit.check_agentic_call(request)
    body = await _parse_agentic_start_body(request)
    session = _get_session_or_404(session_id)
    _authorize_agentic_call(session, body.token, x_demo_token or query_token)

    try:
        candidate_agent, employer_agent = mediator.build_agents(session)
    except mediator.AgenticNotReady as exc:
        raise HTTPException(status_code=412, detail=str(exc))

    try:
        transcript = await mediator.run_agentic_negotiation(session, candidate_agent, employer_agent)
    except negotiation.OfferCheckError as exc:
        _handle_negotiation_error(exc)
    except demo_auth.SpendCapExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    await _maybe_attest(session)
    await _maybe_notify(session)

    return AgenticResult(
        session_id=session.id,
        state=session.state,
        agreed_price=session.agreed_price,
        round_number=session.round_number,
        transcript=[AgenticRoundDetail(**r) for r in transcript],
        attestation=session.attestation,
        tee_attested=settings.tee_mode == "production",
        credential=_credential_response(session),
    )


@router.post("/auth/demo-link", response_model=DemoLinkResponse)
async def create_demo_link_route(
    body: DemoLinkRequest,
    x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
) -> DemoLinkResponse:
    """
    Mints a magic-link token for sharing a session with someone who isn't a
    party to the negotiation (a spectator/prospect watching a demo). Gated
    by OFFERCHECK_INTERNAL_KEY — only the operator can mint these.
    """
    if not settings.offercheck_internal_key or x_internal_key != settings.offercheck_internal_key:
        raise HTTPException(status_code=401, detail="X-Internal-Key required")

    session = _get_session_or_404(body.session_id)
    token, expires_at = demo_auth.generate_token(session.id, body.expires_hours)
    expires_at_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()

    demo_url = f"{settings.offercheck_demo_base_url}/offercheck/demo?token={token}&session={session.id}"
    return DemoLinkResponse(demo_url=demo_url, token=token, expires_at=expires_at_iso)


@router.get("/auth/verify", response_model=VerifyTokenResponse)
async def verify_demo_token_route(token: str, session: str) -> VerifyTokenResponse:
    """Lets the frontend check a magic link's validity before showing the negotiate button."""
    _get_session_or_404(session)  # 404 if the session itself doesn't exist
    try:
        expires_at = demo_auth.verify_token(session, token)
    except demo_auth.InvalidToken as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    if demo_auth.is_consumed(token):
        raise HTTPException(status_code=401, detail="token already used")

    expires_at_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
    return VerifyTokenResponse(valid=True, session_id=session, expires_at=expires_at_iso)


@router.post("/sessions/{session_id}/start-agentic-package", response_model=PackageAgenticResult)
async def start_agentic_package_route(
    session_id: str,
    request: Request,
    x_demo_token: str | None = Header(default=None, alias="X-Demo-Token"),
    query_token: str | None = Query(default=None, alias="token"),
) -> PackageAgenticResult:
    """
    Phase 2B (offercheck_phase2_spec.md): runs PackageCandidateAgent vs
    PackageEmployerAgent to completion over the full compensation package —
    base, equity, signing bonus, annual bonus %, remote policy, start date,
    PTO — negotiated simultaneously each round, not just base salary.

    Separate from /start-agentic (Phase 2A) rather than a mode flag on it:
    a package can't flow through the scalar state machine's float `value`,
    so this drives a parallel package state machine (app.offercheck.package)
    instead — same turn-alternation and max-rounds-then-expire shape, just
    package-typed. Requires both sides to have sealed package inputs —
    candidate_package_ask + candidate_total_comp_floor at POST /sessions
    time, employer_total_comp_budget at POST .../employer/band time (on top
    of the band, which doubles as the base-salary bounds for package mode).

    Auth: same magic-link gate as /start-agentic — a party token OR a demo
    token, either is sufficient (see _authorize_agentic_call). Also counts
    against the same per-session Claude-call spend cap and per-IP rate limit.
    """
    rate_limit.check_agentic_call(request)
    body = await _parse_agentic_start_body(request)
    session = _get_session_or_404(session_id)
    _authorize_agentic_call(session, body.token, x_demo_token or query_token)

    try:
        candidate_agent, employer_agent = package_mediator.build_package_agents(session)
    except package.PackageNotReady as exc:
        raise HTTPException(status_code=412, detail=str(exc))

    try:
        transcript = await package_mediator.run_package_negotiation(session, candidate_agent, employer_agent)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except demo_auth.SpendCapExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    await _maybe_attest_package(session)
    await _maybe_notify_package(session)

    return PackageAgenticResult(
        session_id=session.id,
        state=session.package_state,
        agreed_package=OfferPackage(**session.package_agreed) if session.package_agreed else None,
        round_number=session.package_round_number,
        transcript=[PackageRoundDetail(**r) for r in transcript],
        attestation=session.package_attestation,
        tee_attested=settings.tee_mode == "production",
        credential=_package_credential_response(session),
    )
