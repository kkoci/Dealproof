"""
Fundraising diligence API routes.

Original phases (unchanged):
  Phase 1: POST /api/fundraising/diligence/ingest
  Phase 3: POST /api/fundraising/diligence/{id}/evaluate
           GET  /api/fundraising/diligence/{id}

Negotiation Extension:
  Ext-Phase 1: POST /api/fundraising/diligence/{id}/investor-thresholds
"""
import uuid
import json
import hashlib
import dataclasses
import logging
from fastapi import APIRouter, HTTPException

from app.fundraising.schemas import (
    DiligenceIngestRequest,
    DiligenceIngestResponse,
    DiligenceEvaluateRequest,
    DiligenceEvaluateResponse,
    InvestorThresholds,
    InvestorThresholdsResponse,
)
from app.fundraising.metrics_hasher import (
    hash_metrics_record,
    compute_metrics_corpus_root,
    extract_metric_evidence,
)
from app.fundraising.agents.metrics_inspector import MetricsInspectorAgent
from app.fundraising.agents.metrics_evaluator import MetricsEvaluatorAgent, EvaluationReport
from app.tee.attestation import sign_result
import app.db as db

router = APIRouter(prefix="/api/fundraising")
logger = logging.getLogger(__name__)


@router.post("/diligence/ingest", response_model=DiligenceIngestResponse, status_code=200)
async def ingest_diligence(payload: DiligenceIngestRequest) -> DiligenceIngestResponse:
    """
    Ingest a founder's financial metrics package into the TEE.

    Computes:
      - per-record SHA-256 hashes
      - length-prefixed Merkle corpus root (same algorithm as transcript corpora)
      - deterministic metric evidence extraction (no LLM)

    Persists to fundraising_diligences table and returns corpus_root +
    metric_evidence_preview so the caller can verify hashes match before
    proceeding to Phase 2 evaluation.
    """
    diligence_id = payload.diligence_id or str(uuid.uuid4())

    records_as_dicts = [r.model_dump() for r in payload.metrics_records]

    record_hashes = [hash_metrics_record(r) for r in records_as_dicts]
    corpus_root = compute_metrics_corpus_root(records_as_dicts)
    metric_evidence = extract_metric_evidence(records_as_dicts)

    await db.create_diligence(
        diligence_id=diligence_id,
        company_name=payload.company_name,
        round_label=payload.round_label,
        corpus_root=corpus_root,
        record_hashes=record_hashes,
        metric_evidence=metric_evidence,
    )

    logger.info(
        f"Diligence {diligence_id} ingested — company={payload.company_name}, "
        f"records={len(records_as_dicts)}, corpus_root={corpus_root[:16]}..."
    )

    return DiligenceIngestResponse(
        diligence_id=diligence_id,
        company_name=payload.company_name,
        round_label=payload.round_label,
        corpus_root=corpus_root,
        record_hashes=record_hashes,
        metric_evidence_preview=metric_evidence,
    )


@router.get("/diligence/{diligence_id}", status_code=200)
async def get_diligence_status(diligence_id: str) -> dict:
    """Fetch a diligence record — returns status + credential if evaluated."""
    row = await db.get_diligence(diligence_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Diligence '{diligence_id}' not found.")
    return {
        "diligence_id": row["diligence_id"],
        "company_name": row["company_name"],
        "round_label": row["round_label"],
        "corpus_root": row["metrics_corpus_root"],
        "status": row["status"],
        "credential": row["credential"],
        "tee_quote": row["tee_quote"],
        "created_at": row["created_at"],
    }


@router.post(
    "/diligence/{diligence_id}/evaluate",
    response_model=DiligenceEvaluateResponse,
    status_code=200,
)
async def evaluate_diligence(
    diligence_id: str,
    payload: DiligenceEvaluateRequest,
) -> DiligenceEvaluateResponse:
    """
    Run MetricsInspectorAgent (deterministic) + MetricsEvaluatorAgent (LLM) over
    an ingested diligence package.

    Produces a FundraisingDiligenceCredential with:
      - Hard inspector findings (authoritative, no LLM)
      - LLM qualitative assessment (non-fatal — null if evaluator fails)
      - credential_hash = SHA-256(canonical fields) — in TDX report_data
      - TDX quote binding corpus_root + credential_hash + any_flag_raised

    Idempotent: if already evaluated, returns the stored credential.
    """
    row = await db.get_diligence(diligence_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Diligence '{diligence_id}' not found.")

    # Idempotent — return stored credential if already evaluated
    if row["status"] == "evaluated" and row["credential"]:
        cred = row["credential"]
        return DiligenceEvaluateResponse(
            diligence_id=diligence_id,
            company_name=row["company_name"],
            round_label=row["round_label"],
            corpus_root=row["metrics_corpus_root"],
            credential_hash=cred.get("credential_hash", row["quality_hash"] or ""),
            any_flag_raised=cred.get("any_flag_raised", False),
            inspector_findings=cred.get("inspector_findings", {}),
            evaluation=cred.get("evaluation"),
            tee_quote=row["tee_quote"] or "",
            evaluator_available=cred.get("evaluation") is not None,
        )

    metric_evidence = row["metric_evidence"]

    # ------------------------------------------------------------------ #
    # Step 1 — deterministic inspector (no LLM, no network)
    # ------------------------------------------------------------------ #
    inspector = MetricsInspectorAgent()
    inspection = inspector.inspect(metric_evidence, payload.claimed_values)
    inspector_dict = dataclasses.asdict(inspection)

    # ------------------------------------------------------------------ #
    # Step 2 — LLM evaluator (non-fatal)
    # ------------------------------------------------------------------ #
    evaluator = MetricsEvaluatorAgent()
    evaluation: EvaluationReport | None = None
    evaluator_available = True
    try:
        evaluation = await evaluator.evaluate(
            metric_evidence,
            inspection,
            row["company_name"],
            row["round_label"],
        )
    except Exception as exc:
        evaluator_available = False
        logger.warning(f"MetricsEvaluatorAgent failed for {diligence_id}: {type(exc).__name__}: {exc}")

    evaluation_dict = dataclasses.asdict(evaluation) if evaluation else None

    # ------------------------------------------------------------------ #
    # Step 3 — build credential + credential_hash
    # ------------------------------------------------------------------ #
    credential_fields: dict = {
        "diligence_id": diligence_id,
        "company_name": row["company_name"],
        "round_label": row["round_label"],
        "corpus_root": row["metrics_corpus_root"],
        "inspector_findings": inspector_dict,
        "evaluation": evaluation_dict,
        "any_flag_raised": inspection.any_flag_raised,
    }
    credential_hash = hashlib.sha256(
        json.dumps(credential_fields, sort_keys=True).encode()
    ).hexdigest()

    credential_fields["credential_hash"] = credential_hash

    # ------------------------------------------------------------------ #
    # Step 4 — TDX attestation
    # ------------------------------------------------------------------ #
    tee_quote = await sign_result({
        "corpus_root": row["metrics_corpus_root"],
        "credential_hash": credential_hash,
        "any_flag_raised": inspection.any_flag_raised,
    })

    # ------------------------------------------------------------------ #
    # Step 5 — persist
    # ------------------------------------------------------------------ #
    await db.update_diligence_credential(
        diligence_id=diligence_id,
        credential=credential_fields,
        credential_hash=credential_hash,
        tee_quote=tee_quote,
    )

    logger.info(
        f"Diligence {diligence_id} evaluated — company={row['company_name']}, "
        f"any_flag_raised={inspection.any_flag_raised}, "
        f"evaluator_available={evaluator_available}, "
        f"credential_hash={credential_hash[:16]}..."
    )

    return DiligenceEvaluateResponse(
        diligence_id=diligence_id,
        company_name=row["company_name"],
        round_label=row["round_label"],
        corpus_root=row["metrics_corpus_root"],
        credential_hash=credential_hash,
        any_flag_raised=inspection.any_flag_raised,
        inspector_findings=inspector_dict,
        evaluation=evaluation_dict,
        tee_quote=tee_quote,
        evaluator_available=evaluator_available,
    )


# ---------------------------------------------------------------------------
# Negotiation Extension — Ext-Phase 1
# ---------------------------------------------------------------------------

_VALID_DISCLOSURE_LEVELS = {"none", "category_only", "full_threshold"}


@router.post(
    "/diligence/{diligence_id}/investor-thresholds",
    response_model=InvestorThresholdsResponse,
    status_code=201,
)
async def submit_investor_thresholds(
    diligence_id: str,
    payload: InvestorThresholds,
) -> InvestorThresholdsResponse:
    """
    Store an investor's private diligence thresholds for a given diligence_id.

    The payload is intentionally separate from the founder's ingest/evaluate
    endpoints — founders have no visibility into this endpoint or its data.

    disclosure_on_mismatch controls what the founder learns if a threshold
    isn't met (only the investor chooses this level, not the founder):
      "none"           — founder sees only overall_match bool
      "category_only"  — founder sees which metric names failed (default)
      "full_threshold" — founder sees the investor's exact threshold value

    Returns a threshold_id the investor uses when calling the match endpoint.
    The raw threshold values are never returned here — the caller already
    knows what they submitted.
    """
    if payload.disclosure_on_mismatch not in _VALID_DISCLOSURE_LEVELS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"disclosure_on_mismatch must be one of "
                f"{sorted(_VALID_DISCLOSURE_LEVELS)}, "
                f"got {payload.disclosure_on_mismatch!r}"
            ),
        )

    # Confirm the diligence exists before linking thresholds to it
    row = await db.get_diligence(diligence_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Diligence '{diligence_id}' not found.",
        )

    threshold_id = str(uuid.uuid4())

    await db.save_investor_thresholds(
        threshold_id=threshold_id,
        diligence_id=diligence_id,
        investor_id=payload.investor_id,
        thresholds=payload.model_dump(),
        disclosure_on_mismatch=payload.disclosure_on_mismatch,
    )

    # Fetch back the created_at so the response is accurate
    record = await db.get_investor_thresholds(threshold_id)

    logger.info(
        f"Investor thresholds stored — threshold_id={threshold_id}, "
        f"diligence_id={diligence_id}, investor_id={payload.investor_id}, "
        f"disclosure={payload.disclosure_on_mismatch}"
    )

    return InvestorThresholdsResponse(
        threshold_id=threshold_id,
        diligence_id=diligence_id,
        investor_id=payload.investor_id,
        disclosure_on_mismatch=payload.disclosure_on_mismatch,
        created_at=record["created_at"] or "",
    )
