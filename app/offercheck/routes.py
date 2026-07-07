"""
Offer Check routes — /api/offercheck/*. Phase 1: no DB, no auth beyond opaque
per-party tokens. Phase 2 adds TDX attestation on session close and PDF
offer-letter parsing (see build_spec_offer_check.md).

Endpoints:
  POST /sessions                          candidate submits competing offer + ask
  POST /parse-offer-letter                candidate uploads a PDF -> draft fields to review
  POST /sessions/{id}/employer/band       employer's one-time private band -> gap preview
  POST /sessions/{id}/employer/move       employer accepts / counters / walks
  POST /sessions/{id}/candidate/move      candidate accepts / counters / walks
  GET  /sessions/{id}                     viewer-scoped status poll (?token=...)
  GET  /sessions/{id}/attest              TDX attestation receipt (terminal states only)
  GET  /sessions/{id}/dcap-verify         parsed DCAP quote fields for the receipt above

Token identifies the caller as candidate or employer; it is never trusted to
also declare which party it is. Cross-party raw numbers never appear in a
response — only gap_pct, state, round history (moves only), and the
viewer's own current value.
"""
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.offercheck import negotiation, parsing, store, verifier
from app.offercheck.schemas import (
    AttestationReceipt,
    CandidateSubmitRequest,
    CandidateSubmitResponse,
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

router = APIRouter(prefix="/api/offercheck", tags=["offercheck"])


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
    Once a session reaches a terminal state, produce a TDX quote binding the
    outcome + hashes of the private inputs. Runs at most once per session —
    idempotent so callers don't need to track whether attestation already ran.
    """
    if session.state not in negotiation.TERMINAL_STATES or session.attestation is not None:
        return
    session.attestation = await sign_result(negotiation.attested_terms(session))


@router.post("/sessions", response_model=CandidateSubmitResponse)
async def submit_session(body: CandidateSubmitRequest) -> CandidateSubmitResponse:
    consistency = verifier.check_consistency(body.competing_offer, body.candidate_ask)
    session = store.create_session(body.competing_offer, body.candidate_ask, consistency)
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
