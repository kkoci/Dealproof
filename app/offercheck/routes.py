"""
Offer Check routes — /api/offercheck/*.

Phase 1: no DB, no auth beyond opaque per-party tokens.
Phase 2 adds TDX attestation on session close and PDF offer-letter parsing.
Phase 3 adds company auth (API keys), bulk verification, a πCreds-style
conduct credential folded into the same attestation, ATS webhook receivers,
and billing usage tracking (see build_spec_offer_check.md).

Endpoints:
  POST /sessions                          candidate submits competing offer + ask (optional X-API-Key to tag a company)
  POST /parse-offer-letter                candidate uploads a PDF -> draft fields to review
  POST /sessions/{id}/employer/band       employer's one-time private band -> gap preview
  POST /sessions/{id}/employer/move       employer accepts / counters / walks
  POST /sessions/{id}/candidate/move      candidate accepts / counters / walks
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

Token identifies the caller as candidate or employer; it is never trusted to
also declare which party it is. Cross-party raw numbers never appear in a
response — only gap_pct, state, round history (moves only), and the
viewer's own current value. Company auth (Phase 3) sits alongside this, not
in place of it — see CLAUDE.md "Offer Check Architecture".
"""
import logging

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile

from app.config import settings
from app.offercheck import auth, billing, credential, negotiation, parsing, store, verifier
from app.offercheck.agents import mediator
from app.offercheck.integrations import greenhouse, lever, workday
from app.offercheck.integrations._shared import AtsNotConfigured
from app.offercheck.schemas import (
    AgenticResult,
    AgenticRoundDetail,
    AgenticStartRequest,
    AtsConnectRequest,
    AtsConnectResponse,
    AtsProvider,
    AttestationReceipt,
    BulkVerifyRequest,
    BulkVerifyResponse,
    BulkVerifyResult,
    CandidateSubmitRequest,
    CandidateSubmitResponse,
    CompanyRegisterRequest,
    CompanyRegisterResponse,
    CompanySessionSummary,
    CompanySessionsResponse,
    CredentialResponse,
    DcapVerification,
    EmployerBandRequest,
    EmployerBandResponse,
    ExtractedOfferFields,
    MoveRequest,
    OfferLetterExtraction,
    RoundSummary,
    SessionView,
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
        history=[RoundSummary(round_number=r.round_number, actor=r.actor, move=r.move) for r in session.history],
        consistency=session.consistency,
        agreed_price=session.agreed_price,
        my_current_value=my_value,
        agentic_ready=session.candidate_floor is not None and session.employer_authority_limit is not None,
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
    if isinstance(exc, (negotiation.SessionTerminal, negotiation.BandAlreadySet)):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, negotiation.BandNotSet):
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


@router.post("/sessions", response_model=CandidateSubmitResponse)
async def submit_session(
    body: CandidateSubmitRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> CandidateSubmitResponse:
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


@router.post("/sessions/{session_id}/start-agentic", response_model=AgenticResult)
async def start_agentic_route(session_id: str, body: AgenticStartRequest) -> AgenticResult:
    """
    Phase 2A (offercheck_phase2_spec.md): runs CandidateAgent vs EmployerAgent
    to completion over the same state machine a human would drive. Requires
    both sides to have already sealed their private inputs — candidate_floor
    at POST /sessions time, employer_authority_limit at POST .../employer/band
    time. Either party's token may trigger it once both are sealed; by then
    there's nothing left for either party to unilaterally control.
    """
    session = _get_session_or_404(session_id)
    _resolve_viewer(session, body.token)

    try:
        candidate_agent, employer_agent = mediator.build_agents(session)
    except mediator.AgenticNotReady as exc:
        raise HTTPException(status_code=412, detail=str(exc))

    try:
        transcript = await mediator.run_agentic_negotiation(session, candidate_agent, employer_agent)
    except negotiation.OfferCheckError as exc:
        _handle_negotiation_error(exc)

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
