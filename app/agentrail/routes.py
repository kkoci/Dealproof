"""
Agent Rail — Phase 2 API.

POST /api/agentrail/deals            create a deal room, kick off negotiation in the background
GET  /api/agentrail/deals/{id}       poll status — transcript fills in live as rounds complete
GET  /api/agentrail/deals/{id}/attest  DCAP attestation receipt for an agreed deal

Negotiation runs as a background asyncio task so the create call returns
immediately (deal_id, status="negotiating") and the frontend polls GET for
live progress — this repo has no websocket infra and the spec doesn't call
for one, so on_round (see app/agentrail/mediator.py) writing straight into
the in-memory store is the simplest thing that gives a live-updating view.
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.agentrail import store
from app.agentrail.api_schemas import (
    AttestResponse,
    DealCreateRequest,
    DealCreateResponse,
    DealStatusResponse,
    ProcurementRoundOut,
)
from app.agentrail.buyer_agent import BuyerAgent
from app.agentrail.mediator import run_procurement_negotiation
from app.agentrail.supplier_agent import SupplierAgent
from app.agentrail.verify_quote import verify_quote

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agentrail", tags=["agent-rail"])


@router.post("/deals", response_model=DealCreateResponse, status_code=201)
async def create_deal(payload: DealCreateRequest) -> DealCreateResponse:
    deal_id = str(uuid.uuid4())
    store.create(deal_id, max_rounds=payload.max_rounds)

    buyer = BuyerAgent(
        product=payload.buyer.product,
        quantity=payload.buyer.quantity,
        budget_ceiling=payload.buyer.budget_ceiling,
        min_spec=payload.buyer.min_spec,
        urgency=payload.buyer.urgency,
    )
    supplier = SupplierAgent(
        product=payload.supplier.product,
        floor_price_bulk=payload.supplier.floor_price_bulk,
        floor_price_standard=payload.supplier.floor_price_standard,
        bulk_threshold=payload.supplier.bulk_threshold,
        available_inventory=payload.supplier.available_inventory,
        lead_time_days=payload.supplier.lead_time_days,
    )

    asyncio.create_task(_run_negotiation(deal_id, buyer, supplier, payload.max_rounds))

    return DealCreateResponse(deal_id=deal_id, status=store.STATUS_NEGOTIATING)


@router.get("/deals/{deal_id}", response_model=DealStatusResponse)
async def get_deal(deal_id: str) -> DealStatusResponse:
    record = store.get(deal_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    return DealStatusResponse(
        deal_id=record.deal_id,
        status=record.status,
        max_rounds=record.max_rounds,
        transcript=[
            ProcurementRoundOut(
                round=r.round, role=r.role, action=r.action,
                price=r.price, quantity=r.quantity, terms=r.terms, reasoning=r.reasoning,
            )
            for r in record.transcript
        ],
        final_price=record.final_price,
        final_quantity=record.final_quantity,
        terms=record.terms,
        attestation=record.attestation,
        error=record.error,
    )


@router.get("/deals/{deal_id}/attest", response_model=AttestResponse)
async def get_attestation(deal_id: str) -> AttestResponse:
    record = store.get(deal_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if record.status != store.STATUS_AGREED or not record.attestation:
        raise HTTPException(status_code=409, detail="Deal has no attestation yet — not agreed")

    verification = verify_quote(record.attestation)
    return AttestResponse(
        deal_id=deal_id,
        attestation=record.attestation,
        valid=verification["valid"],
        mode=verification["mode"],
        mrenclave=verification["mrenclave"],
        byte_length=verification["byte_length"],
    )


async def _run_negotiation(deal_id: str, buyer: BuyerAgent, supplier: SupplierAgent, max_rounds: int) -> None:
    async def on_round(round_):
        store.append_round(deal_id, round_)

    try:
        result = await run_procurement_negotiation(buyer, supplier, max_rounds=max_rounds, on_round=on_round)
    except Exception as exc:
        logger.exception(f"Deal {deal_id}: negotiation failed")
        store.mark_failed(deal_id, str(exc))
        return

    if result.agreed:
        store.mark_agreed(deal_id, result.final_price, result.final_quantity, result.terms or {}, result.attestation)
    else:
        store.mark_no_deal(deal_id)
