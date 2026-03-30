"""
API routes — Phase 6.

Changes from Phase 3:
  - _negotiate_deal() gains Step 0: DKIM email proof verification.
    If seller_email_eml is present, verify_email_proof() runs inside the TEE
    before Props verification or negotiation.  The verified domain (or failure
    reason) is stored in the verification dict under the 'dkim' key and
    returned in DealResult.dkim_verification.  The SellerAgent is initialised
    with verified_domain so the TEE-verified credential is present in context
    throughout negotiation.
  - GET /api/deals/{id}/dcap-verify — new Phase 7 endpoint that parses the
    raw TDX attestation quote for a deal and returns structured DCAP header
    fields (version, TEE type, QE vendor ID, report_data hash).

Changes from Phase 2→3 are preserved unchanged.
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException

from app.api.schemas import DealCreate, DealResult, DealStatus, NegotiationRound, DCAPVerification
from app.agents.buyer import BuyerAgent
from app.agents.seller import SellerAgent
from app.agents.negotiation import run_negotiation
from app.props.verifier import verify_data_authenticity
from app.dkim.verifier import verify_email_proof
from app.tee.dcap import parse_tdx_quote
from app.contract.escrow import (
    create_deal_on_chain,
    complete_deal_on_chain,
    EscrowNotConfigured,
)
import app.db as db

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _negotiate_deal(deal_id: str, payload: DealCreate) -> DealResult:
    """
    Core TEE-aware negotiation flow — Phase 6 version.

    Steps:
    0. If seller_email_eml is present, run DKIM email proof verification inside
       the TEE.  Extract the sending domain for injection into the seller agent.
       (Non-fatal: a DKIM failure is recorded but does NOT block negotiation.)
    1. If seller_proof is present, run Props verification inside TEE.
       Fail fast with HTTP 400 if verification fails.
    1b. Deposit ETH escrow on-chain (Phase 4, optional).
    2. Mark deal as 'negotiating' in DB (with verification result persisted).
    3. Run buyer–seller negotiation loop.  Pass data_hash when verification
       passed so the final TDX quote covers both deal terms and data hash.
       Pass verified_domain to SellerAgent for DKIM credential injection.
    3b. Release or note escrow outcome (Phase 4, optional).
    4. Persist result and return DealResult including all attestations.
    """
    # ------------------------------------------------------------------ #
    # Step 0 — DKIM email proof verification (Phase 6)
    # ------------------------------------------------------------------ #
    dkim_result_dict: dict | None = None
    verified_domain: str | None = None

    if payload.seller_email_eml:
        logger.info(f"Deal {deal_id}: running DKIM email proof verification")
        dkim_result = await verify_email_proof(payload.seller_email_eml)
        dkim_result_dict = {
            "domain": dkim_result.domain,
            "verified": dkim_result.verified,
            "dns_unavailable": dkim_result.dns_unavailable,
            "error": dkim_result.error,
        }
        if dkim_result.verified and dkim_result.domain:
            verified_domain = dkim_result.domain
            logger.info(f"Deal {deal_id}: DKIM verified — seller domain is {verified_domain}")
        else:
            logger.warning(
                f"Deal {deal_id}: DKIM verification did not pass "
                f"(domain={dkim_result.domain}, error={dkim_result.error}) — "
                "continuing without verified identity credential"
            )

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
    # Step 1b — on-chain escrow deposit (Phase 4, optional)
    # ------------------------------------------------------------------ #
    escrow_tx: str | None = None
    if payload.seller_address and payload.escrow_amount_eth:
        try:
            value_wei = int(payload.escrow_amount_eth * 1e18)
            escrow_tx = await create_deal_on_chain(
                deal_id=deal_id,
                seller_address=payload.seller_address,
                data_hash=payload.data_hash,
                value_wei=value_wei,
            )
            logger.info(f"Deal {deal_id}: escrow deposited — tx {escrow_tx}")
        except EscrowNotConfigured:
            logger.warning(f"Deal {deal_id}: CONTRACT_ADDRESS not set, skipping escrow")
        except Exception as exc:
            logger.error(f"Deal {deal_id}: escrow deposit failed — {exc}")

    # ------------------------------------------------------------------ #
    # Step 2 — persist verification result and mark as negotiating
    # ------------------------------------------------------------------ #
    verification_dict: dict | None = None

    if verification_result is not None:
        verification_dict = {
            "verified": verification_result.verified,
            "data_hash": verification_result.data_hash,
            "chunk_count": verification_result.chunk_count,
            "attestation": verification_result.attestation,
        }

    # Merge DKIM result into verification_dict (or create one if Props wasn't run).
    # This ensures the full verification picture is always accessible from the DB.
    if dkim_result_dict is not None:
        if verification_dict is None:
            verification_dict = {}
        verification_dict["dkim"] = dkim_result_dict

    # Status already set to 'negotiating' by the atomic claim in negotiate().
    # Here we only persist the verification result (if any) without
    # re-setting the status — avoids an unnecessary second write.
    if verification_dict is not None:
        await db.update_deal(deal_id, "negotiating", verification=verification_dict)

    # ------------------------------------------------------------------ #
    # Step 3 — negotiation loop
    # ------------------------------------------------------------------ #
    buyer = BuyerAgent(budget=payload.buyer_budget, requirements=payload.buyer_requirements)
    # Phase 6: pass verified_domain so the seller agent receives a TEE-verified
    # DKIM identity credential in its system prompt (only set when DKIM passed).
    seller = SellerAgent(
        floor_price=payload.floor_price,
        data_description=payload.data_description,
        verified_domain=verified_domain,
    )

    result = await run_negotiation(buyer, seller, data_hash=data_hash_for_attestation)

    # ------------------------------------------------------------------ #
    # Step 3b — on-chain deal completion (Phase 4, optional)
    # ------------------------------------------------------------------ #
    completion_tx: str | None = None
    if result.agreed and result.attestation and escrow_tx:
        try:
            completion_tx = await complete_deal_on_chain(
                deal_id=deal_id,
                tee_attestation=result.attestation,
            )
            logger.info(f"Deal {deal_id}: escrow released — tx {completion_tx}")
        except EscrowNotConfigured:
            pass  # already logged at deposit stage
        except Exception as exc:
            logger.error(f"Deal {deal_id}: escrow completion failed — {exc}")
    elif not result.agreed and escrow_tx:
        logger.info(
            f"Deal {deal_id}: negotiation failed — buyer may refund after escrow deadline"
        )

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
        escrow_tx=escrow_tx,
        completion_tx=completion_tx,
        dkim_verification=dkim_result_dict,  # Phase 6: DKIM result (None if not provided)
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

    Uses an atomic DB claim (optimistic lock) to prevent two concurrent
    callers from both running negotiation on the same deal.
    """
    row = await db.get_deal(deal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Deal is already {row['status']}")

    # Atomic claim: only one concurrent caller wins this UPDATE.
    claimed = await db.claim_deal_for_negotiation(deal_id)
    if not claimed:
        raise HTTPException(
            status_code=409,
            detail="Deal negotiation already started by another request",
        )

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


@router.get("/deals/{deal_id}/dcap-verify", response_model=DCAPVerification)
async def get_dcap_verification(deal_id: str) -> DCAPVerification:
    """
    Phase 7: Parse and inspect the TDX attestation quote for a deal.

    This endpoint decodes the raw TDX quote stored in the deal's attestation
    field and returns structured DCAP header fields.

    In simulation mode (TEE_MODE=simulation) the quote is a SHA-256 hash
    prefixed with 'sim_quote:'.  The response will have mode='simulation' and
    verification_status='simulation_only'.

    In production (real Intel TDX CVM) the quote is a hex-encoded binary DCAP
    quote.  The response includes:
      - version: DCAP quote version (typically 4)
      - tee_type: "TDX" (0x00000081) or "SGX" (0x00000000)
      - qe_vendor_id: Intel QE vendor UUID
      - report_data_hex: first 32 bytes of TD report_data (= SHA-256 of deal terms)
      - deal_terms_hash: same value, labelled for UI clarity

    The full on-chain DCAP verification (Intel cert chain, CRL checks, FMSPC
    matching) is Phase 7 and requires a deployed DCAP verifier contract.  This
    endpoint provides the quote parsing layer — sufficient to confirm the TEE
    type and bind the deal terms hash to the attestation.
    """
    row = await db.get_deal(deal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    attestation: str | None = None
    if row["result"]:
        attestation = row["result"].get("attestation")

    if not attestation:
        raise HTTPException(
            status_code=404,
            detail="No attestation available — deal must be in 'agreed' status",
        )

    parsed = parse_tdx_quote(attestation)
    return DCAPVerification(deal_id=deal_id, **parsed)


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
