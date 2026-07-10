"""
Agent Rail API — Phase 2 deal lifecycle + Phase 3 escrow/credential.

POST /api/agentrail/deals               create a deal room, kick off negotiation in the background
GET  /api/agentrail/deals/{id}          poll status — transcript fills in live as rounds complete
GET  /api/agentrail/deals/{id}/attest   DCAP attestation receipt for an agreed deal
GET  /api/agentrail/deals/{id}/credential   πCreds conduct credential (Phase 3, agreed deals only)

Negotiation runs as a background asyncio task so the create call returns
immediately (deal_id, status="negotiating") and the frontend polls GET for
live progress — this repo has no websocket infra and the spec doesn't call
for one, so on_round (see app/agentrail/mediator.py) writing straight into
the in-memory store is the simplest thing that gives a live-updating view.

Phase 3 escrow (deposit at creation, release on agreement) and the conduct
credential are both computed inside _run_negotiation() — the only place that
still has buyer.budget_ceiling/supplier.floor_price_* in scope, since the
store never persists them (see app/agentrail/store.py, app/agentrail/credential.py).
Both are non-fatal, same resilience pattern as DealProof core's Step 1b/3b.
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.agentrail import store
from app.agentrail.api_schemas import (
    AttestResponse,
    ConductCheckOut,
    CredentialResponse,
    DealCreateRequest,
    DealCreateResponse,
    DealStatusResponse,
    ProcurementRoundOut,
)
from app.agentrail.buyer_agent import BuyerAgent
from app.agentrail.credential import audit_procurement_conduct, build_credential
from app.agentrail.escrow import EscrowNotConfigured, deposit_escrow, release_escrow
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

    # Phase 3 — optional on-chain escrow deposit. Not deployed to any live
    # network as of Phase 3, so this raises EscrowNotConfigured and is skipped
    # (logged, non-fatal) unless AGENTRAIL_CONTRACT_ADDRESS is set.
    if payload.supplier_address and payload.escrow_amount_eth:
        try:
            value_wei = int(payload.escrow_amount_eth * 1e18)
            tx = await deposit_escrow(deal_id, payload.supplier_address, value_wei)
            store.set_escrow_tx(deal_id, tx)
            logger.info(f"Deal {deal_id}: escrow deposited — tx {tx}")
        except EscrowNotConfigured:
            logger.warning(f"Deal {deal_id}: AGENTRAIL_CONTRACT_ADDRESS not set, skipping escrow")
        except Exception as exc:
            logger.error(f"Deal {deal_id}: escrow deposit failed — {exc}")

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
        picreds_hash=record.picreds_hash,
        picreds_attested=bool(record.picreds_hash),
        escrow_tx=record.escrow_tx,
        settlement_tx=record.settlement_tx,
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


@router.get("/deals/{deal_id}/credential", response_model=CredentialResponse)
async def get_credential(deal_id: str) -> CredentialResponse:
    record = store.get(deal_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if record.status != store.STATUS_AGREED or record.credential is None:
        raise HTTPException(status_code=409, detail="Deal has no conduct credential yet — not agreed")

    audit_result = record.credential["audit_result"]
    return CredentialResponse(
        deal_id=deal_id,
        credential_type=record.credential["credential_type"],
        checks={k: ConductCheckOut(**v) for k, v in audit_result["checks"].items()},
        genuine_negotiation=audit_result["genuine_negotiation"],
        final_price=audit_result["final_price"],
        picreds_hash=record.picreds_hash,
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

    if not result.agreed:
        store.mark_no_deal(deal_id)
        return

    store.mark_agreed(deal_id, result.final_price, result.final_quantity, result.terms or {}, result.attestation)

    # Phase 3 — conduct credential. Must happen here, not in a later GET handler:
    # buyer.budget_ceiling / supplier.floor_price_* go out of scope once this
    # function returns, and the store never persists them (see credential.py).
    try:
        applicable_floor = (
            supplier.floor_price_bulk if buyer.quantity >= supplier.bulk_threshold
            else supplier.floor_price_standard
        )
        transcript_dicts = [
            {"round": r.round, "role": r.role, "action": r.action, "price": r.price}
            for r in result.transcript
        ]
        audit_result = audit_procurement_conduct(
            transcript_dicts, buyer.budget_ceiling, applicable_floor, result.final_price,
        )
        credential, picreds_hash = build_credential(deal_id, audit_result)
        store.set_credential(deal_id, credential, picreds_hash)
    except Exception as exc:
        logger.warning(f"Deal {deal_id}: conduct credential failed (non-fatal) — {exc}")

    # Phase 3 — release escrow, only if a deposit was made at creation.
    record = store.get(deal_id)
    if record is not None and record.escrow_tx:
        try:
            tx = await release_escrow(deal_id, result.attestation)
            store.set_settlement_tx(deal_id, tx)
            logger.info(f"Deal {deal_id}: escrow released — tx {tx}")
        except EscrowNotConfigured:
            logger.warning(f"Deal {deal_id}: AGENTRAIL_CONTRACT_ADDRESS not set, skipping escrow release")
        except Exception as exc:
            logger.error(f"Deal {deal_id}: escrow release failed — {exc}")
