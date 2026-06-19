"""
Fundraising diligence API routes — Phase 1.

Mounted at /api/fundraising/ alongside existing DealProof routes.
Does not touch the negotiation flow, πCreds logic, or any existing endpoint.
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException

from app.fundraising.schemas import DiligenceIngestRequest, DiligenceIngestResponse
from app.fundraising.metrics_hasher import (
    hash_metrics_record,
    compute_metrics_corpus_root,
    extract_metric_evidence,
)
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
