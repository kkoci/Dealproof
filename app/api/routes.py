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
import hashlib
import json
import time
import uuid
import logging
import httpx
from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    DealCreate, DealResult, DealStatus, NegotiationRound, DCAPVerification,
    AttestationResponse, PiCred,
    CorpusIngest, CorpusIngestResponse,
    TeamCredential, CredentialResponse,
)
from app.agents.buyer import BuyerAgent
from app.agents.seller import SellerAgent
from app.agents.negotiation import run_negotiation
from app.agents.auditor import AuditorAgent
from app.agents.arbitrator import ArbitratorAgent
from app.tee.attestation import get_enclave_quote
from app.props.verifier import verify_data_authenticity
from app.dkim.verifier import verify_email_proof
from app.tee.dcap import parse_tdx_quote
from app.contract.escrow import (
    create_deal_on_chain,
    complete_deal_on_chain,
    EscrowNotConfigured,
)
import app.db as db
from app.memory.client import search_memories, add_memories, get_memory_hash
from app.picreds.auditor import audit_agent_policy, audit_deal_conduct
from app.picreds.credential import make_credential, hash_credentials
from app.props.transcript_hasher import hash_transcript, compute_corpus_root
from app.agents.data_credential import DataCredentialAgent

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _format_memories(results: list[dict]) -> str:
    if not results:
        return ""
    lines = []
    for r in results[:5]:
        content = r.get("content") or r.get("text") or str(r)
        lines.append(f"- {content}")
    return "\n".join(lines)


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
    # Step M1 — recall memory context + snapshot hash before negotiation
    # Search and hash are separated so hash works even if embedding fails.
    # ------------------------------------------------------------------ #
    buyer_memory_context = ""
    seller_memory_context = ""
    try:
        buyer_memories = await search_memories(
            "buyer",
            f"counterparty offering {payload.data_description} at floor {payload.floor_price}"
        )
        seller_memories = await search_memories(
            "seller",
            f"buyer with budget {payload.buyer_budget} requiring {payload.buyer_requirements}"
        )
        buyer_memory_context = _format_memories(buyer_memories)
        seller_memory_context = _format_memories(seller_memories)
    except Exception as exc:
        logger.warning(f"Deal {deal_id}: memory search failed (non-fatal) — {exc}")

    memory_hash = ""
    try:
        buyer_hash_data = await get_memory_hash("buyer")
        seller_hash_data = await get_memory_hash("seller")
        memory_hash = f"{buyer_hash_data.get('hash', '')}:{seller_hash_data.get('hash', '')}"
    except Exception as exc:
        logger.warning(f"Deal {deal_id}: memory hash failed (non-fatal) — {exc}")

    # Hash the memory context injected into each agent's prompt.
    # Proves which recalled memories shaped agent behaviour — not just that
    # memory state changed, but what content the agents actually received.
    memory_context_hash: str | None = None
    if buyer_memory_context or seller_memory_context:
        memory_context_hash = hashlib.sha256(
            json.dumps(
                {"buyer": buyer_memory_context, "seller": seller_memory_context},
                sort_keys=True,
            ).encode()
        ).hexdigest()

    # ------------------------------------------------------------------ #
    # Step 3 — negotiation loop
    # ------------------------------------------------------------------ #
    buyer = BuyerAgent(
        budget=payload.buyer_budget,
        requirements=payload.buyer_requirements,
        memory_context=buyer_memory_context,
    )
    # Phase 6: pass verified_domain so the seller agent receives a TEE-verified
    # DKIM identity credential in its system prompt (only set when DKIM passed).
    seller = SellerAgent(
        floor_price=payload.floor_price,
        data_description=payload.data_description,
        verified_domain=verified_domain,
        memory_context=seller_memory_context,
    )

    result = await run_negotiation(
        buyer, seller,
        data_hash=data_hash_for_attestation,
        memory_hash=memory_hash,
        arbitrator=ArbitratorAgent(),
    )

    # ------------------------------------------------------------------ #
    # Step M2 — store deal outcome + capture post-deal memory hash (non-fatal)
    #
    # Completing the state transition proof:
    #   memory_hash      = pre-negotiation state (A) — snapshotted in M1
    #   memory_hash_post = post-negotiation state (B) — snapshotted here after storing
    #
    # Both are included in the final TDX attestation so a verifier can prove:
    #   "Code X ran on memory state A, reached outcome Y, and produced memory state B."
    # ------------------------------------------------------------------ #
    memory_hash_post: str | None = None
    memory_write_hash: str | None = None
    picreds_raw: list[dict] = []
    picreds_hash: str | None = None
    audit_report: dict | None = None
    audit_credential_hash: str | None = None
    audit_error: str | None = None
    if result.agreed:
        try:
            outcome_messages = [
                {"role": "user", "content": f"Deal context: {payload.buyer_requirements}. Data: {payload.data_description}."},
                {"role": "assistant", "content": f"Agreed at price {result.final_price}. Terms: {result.terms}."},
            ]
            # Hash the exact content written to memory — proves this specific
            # deal outcome caused the A→B state transition, not a concurrent write.
            memory_write_hash = hashlib.sha256(
                json.dumps(outcome_messages, sort_keys=True).encode()
            ).hexdigest()
            await add_memories("buyer", outcome_messages, user_id=deal_id)
            await add_memories("seller", outcome_messages, user_id=deal_id)
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300] if exc.response.text else "(empty body)"
            logger.warning(
                f"Deal {deal_id}: memory store failed (non-fatal) — "
                f"HTTP {exc.response.status_code} from memory service: {body}"
            )
        except Exception as exc:
            logger.warning(f"Deal {deal_id}: memory store failed (non-fatal) — {exc}")

        try:
            buyer_hash_post = await get_memory_hash("buyer")
            seller_hash_post = await get_memory_hash("seller")
            memory_hash_post = f"{buyer_hash_post.get('hash', '')}:{seller_hash_post.get('hash', '')}"
            logger.info(f"Deal {deal_id}: post-deal memory hash captured")
            # If state didn't change, the write had no effect — null the write hash
            # so it doesn't falsely imply causality (e.g. duplicate deal submission).
            if memory_hash_post == memory_hash:
                memory_write_hash = None
        except Exception as exc:
            logger.warning(f"Deal {deal_id}: post-deal memory hash failed (non-fatal) — {exc}")

        # ------------------------------------------------------------------ #
        # Step P — πCreds: audit agent policy + deal conduct (non-fatal)
        #
        # Policy credentials: read each agent's system prompt inside the TEE
        #   and certify what rules it is bound by, without revealing the prompt.
        # Conduct credential: review the transcript and certify neither agent
        #   violated their hard constraints during this negotiation.
        # ------------------------------------------------------------------ #
        try:
            buyer_code_hash = hashlib.sha256(buyer.system_prompt.encode()).hexdigest()
            seller_code_hash = hashlib.sha256(seller.system_prompt.encode()).hexdigest()

            buyer_policy = await audit_agent_policy("buyer", buyer.system_prompt)
            seller_policy = await audit_agent_policy("seller", seller.system_prompt)

            transcript_data = [
                {"round": r.round, "role": r.role, "action": r.action, "price": r.price}
                for r in result.transcript
            ]
            conduct = await audit_deal_conduct(
                transcript_data, payload.buyer_budget, payload.floor_price, result.final_price
            )

            picreds_raw = [
                make_credential("policy", "buyer_agent", buyer_policy, deal_id, buyer_code_hash),
                make_credential("policy", "seller_agent", seller_policy, deal_id, seller_code_hash),
                make_credential("conduct", "deal", conduct, deal_id, ""),
            ]
            picreds_hash = hash_credentials(picreds_raw)
            logger.info(f"Deal {deal_id}: πCreds issued ({len(picreds_raw)} credentials)")
        except Exception as exc:
            logger.warning(f"Deal {deal_id}: πCreds audit failed (non-fatal) — {exc}")

        # ------------------------------------------------------------------ #
        # Step A — Auditor: TEE compliance witness (non-fatal)
        # ------------------------------------------------------------------ #
        try:
            transcript_data_audit = [
                {"round": r.round, "role": r.role, "action": r.action, "price": r.price}
                for r in result.transcript
            ]
            audit = await AuditorAgent().audit(
                transcript_data_audit, payload.buyer_budget, payload.floor_price, result.final_price
            )
            if audit is not None:
                audit_report = {
                    "genuine_negotiation": audit.genuine_negotiation,
                    "round_count": audit.round_count,
                    "final_price": audit.final_price,
                    "summary": audit.summary,
                    "credential_hash": audit.credential_hash,
                }
                audit_credential_hash = audit.credential_hash
                logger.info(f"Deal {deal_id}: Auditor report produced")
        except Exception as exc:
            audit_error = f"{type(exc).__name__}: {exc}"
            logger.warning(f"Deal {deal_id}: Auditor failed (non-fatal) — {audit_error}")

        # Re-attest with the full evidence chain:
        #   deal terms + memory state A→B + πCreds hash + audit credential hash
        # Fires when any of the above produced real content.
        _post_parts = (memory_hash_post or "").split(":")
        _has_memory = len(_post_parts) == 2 and all(_post_parts)
        _has_picreds = bool(picreds_hash)
        _has_audit = bool(audit_credential_hash)
        _has_memory_context = bool(memory_context_hash)
        if (_has_memory or _has_picreds or _has_audit or _has_memory_context) and result.final_price is not None:
            try:
                from app.tee.attestation import sign_result as _sign_result
                sign_payload: dict = {"final_price": result.final_price, "terms": result.terms or {}}
                if data_hash_for_attestation:
                    sign_payload["data_hash"] = data_hash_for_attestation
                    sign_payload["data_verified"] = True
                if memory_hash:
                    sign_payload["memory_hash"] = memory_hash
                if memory_hash_post:
                    sign_payload["memory_hash_post"] = memory_hash_post
                if _has_memory:
                    sign_payload["memory_attested"] = True
                if picreds_hash:
                    sign_payload["picreds_hash"] = picreds_hash
                    sign_payload["picreds_attested"] = True
                if audit_credential_hash:
                    sign_payload["audit_credential_hash"] = audit_credential_hash
                if memory_context_hash:
                    sign_payload["memory_context_hash"] = memory_context_hash
                if memory_write_hash:
                    sign_payload["memory_write_hash"] = memory_write_hash
                result.attestation = await _sign_result(sign_payload)
                logger.info(f"Deal {deal_id}: re-attested with full evidence chain")
            except Exception as exc:
                logger.warning(f"Deal {deal_id}: evidence chain re-attestation failed (non-fatal) — {exc}")

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
        memory_hash=memory_hash if memory_hash else None,
        memory_hash_post=memory_hash_post,
        memory_attested=bool(memory_hash and result.agreed),
        picreds=[PiCred(**{k: v for k, v in p.items()}) for p in picreds_raw] if picreds_raw else None,
        picreds_hash=picreds_hash,
        picreds_attested=bool(picreds_hash and result.agreed),
        audit_report=audit_report,
        audit_error=audit_error,
        arbitrated=result.arbitrated,
        memory_context_hash=memory_context_hash,
        memory_write_hash=memory_write_hash,
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

@router.get("/attest", response_model=AttestationResponse)
async def get_attestation() -> AttestationResponse:
    """
    Return the current DCAP quote for the running enclave.

    This is the FIRST call a client makes — before sending any sensitive payload.
    Verify the returned quote against Intel's DCAP verification service (or the
    /api/deals/{id}/dcap-verify endpoint), confirm mrenclave matches your trusted
    build measurement, then proceed to POST /api/deals/run.

    No authentication required — this endpoint is public by design.
    """
    result = await get_enclave_quote()
    return AttestationResponse(
        quote=result["quote"],
        mrenclave=result["mrenclave"],
        timestamp=int(time.time()),
    )


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


# ---------------------------------------------------------------------------
# ETHGlobal NYC — TinyCloud corpus ingestion (Milestone 2)
# ---------------------------------------------------------------------------

def _hash_conversation(conversation: dict) -> str | None:
    """
    Hash one TinyCloud conversation to a 64-char hex string.
    Prefers sentences; falls back to a synthetic sentence from summary.
    Returns None if neither is available (caller skips this conversation).
    """
    sentences = conversation.get("sentences") or []
    if sentences:
        return hash_transcript([
            {k: s.get(k) for k in ("index", "speaker_id", "speaker_name", "text", "start_time", "end_time", "language")}
            for s in sentences
        ])
    summary = conversation.get("summary")
    if summary:
        synthetic = {
            "index": 0, "speaker_id": "summary", "speaker_name": "Summary",
            "text": summary, "start_time": None, "end_time": None, "language": "en",
        }
        return hash_transcript([synthetic])
    return None


@router.post("/transcripts/ingest", response_model=CorpusIngestResponse, status_code=200)
async def ingest_corpus(payload: CorpusIngest) -> CorpusIngestResponse:
    """
    Ingest a TinyCloud transcript corpus and compute a Merkle root suitable
    for use as data_hash in POST /api/deals/run.

    direct mode   — supply conversations inline (no TinyCloud auth needed)
    tinycloud mode — fetch conversations + transcripts live from TinyCloud node
                     using tinycloud_session_token
    """
    if payload.mode == "tinycloud":
        if not payload.tinycloud_session_token:
            raise HTTPException(status_code=400, detail="tinycloud_session_token required for tinycloud mode")

        conversations_raw: list[dict] = []
        headers = {"Authorization": f"Bearer {payload.tinycloud_session_token}"}
        host = payload.tinycloud_host.rstrip("/")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Step 1: fetch conversation rows via SQL
                sql_resp = await client.post(
                    f"{host}/v1/sql",
                    json={
                        "database": "xyz.tinycloud.listen/conversations",
                        "query": "SELECT id, title, source, started_at, summary FROM conversation LIMIT 300",
                    },
                    headers=headers,
                )
                sql_resp.raise_for_status()
                rows = sql_resp.json().get("rows", [])

                # Step 2: fetch transcript KV blob per conversation
                for row in rows:
                    conv = {
                        "id": row["id"],
                        "title": row.get("title", ""),
                        "source": row.get("source", ""),
                        "started_at": row.get("started_at", ""),
                        "summary": row.get("summary"),
                        "sentences": [],
                    }
                    kv_key = f"xyz.tinycloud.listen/transcript/{row['id']}"
                    try:
                        kv_resp = await client.get(f"{host}/v1/kv/{kv_key}", headers=headers)
                        if kv_resp.status_code == 200:
                            conv["sentences"] = kv_resp.json()
                    except Exception:
                        pass  # KV miss — summary fallback handled in _hash_conversation
                    conversations_raw.append(conv)

        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=503, detail=f"TinyCloud unavailable: HTTP {exc.response.status_code}")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"TinyCloud unavailable: {exc}")

    else:
        # direct mode — use conversations from request body
        conversations_raw = [c.model_dump() for c in payload.conversations]

    # Hash each conversation
    per_conv_hashes: list[str] = []
    hashable_convs: list[dict] = []
    summaries_available = sum(1 for c in conversations_raw if c.get("summary"))

    for conv in conversations_raw:
        h = _hash_conversation(conv)
        if h is not None:
            per_conv_hashes.append(h)
            hashable_convs.append(conv)
        else:
            logger.warning(f"Corpus {payload.corpus_id}: skipping conversation {conv.get('id')} — no sentences or summary")

    if not per_conv_hashes:
        raise HTTPException(status_code=400, detail="Corpus produced no hashable content — all conversations lack sentences and summary")

    corpus_root = compute_corpus_root(per_conv_hashes)
    seller_proof = {
        "root_hash": corpus_root,
        "chunk_hashes": per_conv_hashes,
        "chunk_count": len(per_conv_hashes),
        "algorithm": "sha256",
    }

    await db.save_corpus(payload.corpus_id, hashable_convs, corpus_root)
    logger.info(f"Corpus {payload.corpus_id}: ingested {len(hashable_convs)} conversations, root={corpus_root[:16]}...")

    return CorpusIngestResponse(
        corpus_id=payload.corpus_id,
        conversation_count=len(hashable_convs),
        corpus_root=corpus_root,
        seller_proof=seller_proof,
        summaries_available=summaries_available,
    )


@router.post("/deals/{deal_id}/credential", response_model=CredentialResponse, status_code=200)
async def issue_credential(deal_id: str) -> CredentialResponse:
    """
    Issue a TEE-attested TeamDynamicsCredential for an agreed deal.

    Requires:
    - Deal must be in 'agreed' status
    - Deal's data_hash must match a corpus ingested via POST /api/transcripts/ingest

    Runs DataCredentialAgent on the stored conversations inside the TEE and
    returns a TDX-attested credential. Assessment failures are attested
    transparently — {"error": "assessment_failed"} is a valid attested subject.
    """
    from datetime import datetime
    from app.tee.attestation import sign_result as _sign_result

    row = await db.get_deal(deal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    if row["status"] != "agreed":
        raise HTTPException(status_code=409, detail="Deal is not agreed — credential requires an agreed deal")

    corpus_root = row["payload"].get("data_hash")
    if not corpus_root:
        raise HTTPException(status_code=404, detail="Deal has no data_hash — cannot look up corpus")

    corpus = await db.get_corpus_by_root(corpus_root)
    if corpus is None:
        raise HTTPException(
            status_code=404,
            detail="No corpus found for this deal's data_hash — ingest via POST /api/transcripts/ingest first",
        )

    assessment = await DataCredentialAgent().assess(corpus["conversations"])

    issued_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    credential = TeamCredential(
        issued_at=issued_at,
        deal_id=deal_id,
        corpus_root=corpus_root,
        subject=assessment,
    )

    sign_payload = {
        "credential_type": credential.credential_type,
        "deal_id": deal_id,
        "corpus_root": corpus_root,
        "issued_at": issued_at,
        "subject": assessment,
    }
    attestation = await _sign_result(sign_payload)
    logger.info(f"Deal {deal_id}: TeamDynamicsCredential issued and attested")

    return CredentialResponse(
        deal_id=deal_id,
        credential=credential,
        attestation=attestation,
        verifiable=True,
    )
