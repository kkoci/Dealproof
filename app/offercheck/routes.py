"""
Offer Check routes — /api/offercheck/*. Phase 1: no TEE, no DB, no auth
beyond opaque per-party tokens (see build_spec_offer_check.md).

Endpoints:
  POST /sessions                          candidate submits competing offer + ask
  POST /sessions/{id}/employer/band       employer's one-time private band -> gap preview
  POST /sessions/{id}/employer/move       employer accepts / counters / walks
  POST /sessions/{id}/candidate/move      candidate accepts / counters / walks
  GET  /sessions/{id}                     viewer-scoped status poll (?token=...)

Token identifies the caller as candidate or employer; it is never trusted to
also declare which party it is. Cross-party raw numbers never appear in a
response — only gap_pct, state, round history (moves only), and the
viewer's own current value.
"""
from fastapi import APIRouter, HTTPException

from app.offercheck import negotiation, store, verifier
from app.offercheck.schemas import (
    CandidateSubmitRequest,
    CandidateSubmitResponse,
    EmployerBandRequest,
    EmployerBandResponse,
    MoveRequest,
    RoundSummary,
    SessionView,
)
from app.offercheck.store import Session

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
    return _view_for(session, "candidate")


@router.get("/sessions/{session_id}", response_model=SessionView)
async def get_session_view(session_id: str, token: str) -> SessionView:
    session = _get_session_or_404(session_id)
    viewer = _resolve_viewer(session, token)
    return _view_for(session, viewer)
