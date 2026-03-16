"""
API routes — Phase 3.

Changes from Phase 2:
  - _negotiate_deal() now runs the Props verification gate before starting
    the negotiation loop.  If seller_proof is provided and verification fails,
    the deal is marked 'verification_failed' and HTTP 400 is returned — the
    negotiation never starts.
  - On success, the VerificationResult's attestation is stored separately in
    the DB (verification column) and returned in DealResult as
    data_verification_attestation.
  - run_negotiation() is called with data_hash when verification passed, so
    the combined negotiation TDX quote covers both deal terms and data hash.
  - GET /api/deals/{id}/verification  — new endpoint returning the Props
    verification result for a deal.
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException

from app.api.schemas import DealCreate, DealResult, DealStatus, NegotiationRound
from app.agents.buyer import BuyerAgent
from app.agents.seller import SellerAgent
from app.agents.negotiation import run_negotiation
from app.props.verifier import verify_data_authenticity
import app.db as db

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _negotiate_deal(deal_id: str, payload: DealCreate) -> DealResult:
    """
    Core TEE-aware negotiation flow — Phase 3 version.

    Steps:
    1. If seller_proof is present, run Props verification inside TEE.
       Fail fast with HTTP 400 if verification fails.
    2. Mark deal as 'negotiating' in DB (with verification result persisted).
    3. Run buyer–seller negotiation loop.  Pass data_hash when verification
       passed so the final TDX quote covers both deal terms and data hash.
    4. Persist result and return DealResult including both attestations.
    """
    # ------------------------------------------------------------------ #
    # Step 1 — Props verification gate (Phase 3)
    # ------------------------------------------------------------------ #
    verification_result = None
    data_hash_for_attestation: str | None = None

    if payload.seller_proof is not None:
        logger.info(f"Deal {deal_id}: running Props verification")
        verification_result = await verify_data_authenticity(
            payload.data_hash, payload.seller_proof
        )

        if not verification_result.verified:
            await db.update_deal(
                deal_id,
                "verification_failed",
                verification={"verified": False, "error": verification_result.error},
            )
            logger.warning(f"Deal {deal_id}: verification failed — {verification_result.error}")
            raise HTTPException(
                status_code=400,
                detail=f"Data verification failed: {verification_result.error}",
            )

        logger.info(f"Deal {deal_id}: verification passed ({verification_result.chunk_count} chunks)")
        data_hash_for_attestation = payload.data_hash

    # ------------------------------------------------------------------ #
    # Step 2 — persist verification result and mark as negotiating
    # ------------------------------------------------------------------ #
    verification_dict = (
        {
            "verified": verification_result.verified,
            "data_hash": verification_result.data_hash,
            "chunk_count": verification_result.chunk_count,
            "attestation": verification_result.attestation,
        }
        if verification_result is not None
        else None
    )

    await db.update_deal(deal_id, "negotiating", verification=verification_dict)

    # ------------------------------------------------------------------ #
    # Step 3 — negotiation loop
    # ------------------------------------------------------------------ #
    buyer = BuyerAgent(budget=payload.buyer_budget, requirements=payload.buyer_requirements)
    seller = SellerAgent(floor_price=payload.floor_price, data_description=payload.data_description)

    result = await run_negotiation(buyer, seller, data_hash=data_hash_for_attestation)

    # ------------------------------------------------------------------ #
    # Step 4 — persist and return
    # ------------------------------------------------------------------ #
    deal_result = DealResult(
        deal_id=deal_id,
        agreed=result.agreed,
        final_price=result.final_price,
        terms=result.terms,
        attestation=result.attestation,
        data_verification_attestation=(
            verification_result.attestation if verification_result else None
        ),
        transcript=[
            NegotiationRound(
                round=r.round,
                role=r.role,
                action=r.action,
                price=r.price,
                terms=r.terms,
                reasoning=r.reasoning,
            )
            for r in result.transcript
        ],
    )

    final_status = "agreed" if result.agreed else "failed"
    await db.update_deal(
        deal_id,
        final_status,
        result=deal_result.model_dump(),
        verification=verification_dict,
    )
    logger.info(f"Deal {deal_id} finished: {final_status}")
    return deal_result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/deals", response_model=DealStatus, status_code=201)
async def create_deal(payload: DealCreate) -> DealStatus:
    """
    Create a deal and persist the full payload (including seller_proof if
    provided) in SQLite.  Returns a DealStatus with status='pending'.
    Call POST /api/deals/{id}/negotiate next to run the verification +
    negotiation flow.
    """
    deal_id = str(uuid.uuid4())
    await db.create_deal(deal_id, payload.model_dump())
    logger.info(f"Deal created: {deal_id}")
    return DealStatus(deal_id=deal_id, status="pending")


@router.post("/deals/{deal_id}/negotiate", response_model=DealResult)
async def negotiate(deal_id: str) -> DealResult:
    """
    Run Props verification + TEE negotiation for a previously created deal.
    Retrieves the stored DealCreate payload (including seller_proof) from
    SQLite and runs the full Phase 3 flow.
    """
    row = await db.get_deal(deal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Deal is already {row['status']}")

    payload = DealCreate(**row["payload"])
    return await _negotiate_deal(deal_id, payload)


@router.post("/deals/run", response_model=DealResult, status_code=200)
async def create_and_negotiate(payload: DealCreate) -> DealResult:
    """
    Convenience endpoint: create a deal and run Props verification +
    negotiation in a single call.  seller_proof is optional — omitting it
    skips data verification and runs the Phase 1/2 flow.
    """
    deal_id = str(uuid.uuid4())
    await db.create_deal(deal_id, payload.model_dump())
    return await _negotiate_deal(deal_id, payload)


@router.get("/deals/{deal_id}/status", response_model=DealStatus)
async def get_status(deal_id: str) -> DealStatus:
    row = await db.get_deal(deal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    result = DealResult(**row["result"]) if row["result"] else None
    return DealStatus(deal_id=row["id"], status=row["status"], result=result)


@router.get("/deals/{deal_id}/attestation")
async def get_attestation(deal_id: str) -> dict:
    """
    Return the negotiation TDX attestation quote for an agreed deal.
    This quote covers final_price + terms, and also data_hash + data_verified
    when a seller_proof was submitted.
    """
    row = await db.get_deal(deal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if not row["result"] or not row["result"].get("attestation"):
        raise HTTPException(
            status_code=404,
            detail="No attestation available — deal must be in 'agreed' status",
        )
    return {"deal_id": deal_id, "attestation": row["result"]["attestation"]}


@router.get("/deals/{deal_id}/verification")
async def get_verification(deal_id: str) -> dict:
    """
    Return the Props data verification result for a deal.

    Present when the deal was created with a seller_proof.  Contains:
      - verified: bool
      - data_hash: str
      - chunk_count: int
      - attestation: TDX quote covering the verification (str | null)
    """
    row = await db.get_deal(deal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if row["verification"] is None:
        raise HTTPException(
            status_code=404,
            detail="No verification record — deal was created without a seller_proof",
        )
    return {"deal_id": deal_id, "verification": row["verification"]}
