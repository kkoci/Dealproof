"""
SOC 2 continuous assurance endpoints — product/continuous-soc2.

Phase 1:
  POST /api/soc2/audits/ingest  — upload config files, get corpus root + evidence preview

The negotiation flow, πCreds logic, and agent behavior are untouched.
This router is mounted alongside the existing API under /api/soc2/.
"""
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import app.db as db
from app.soc2.config_hasher import (
    hash_config_file,
    compute_config_corpus_root,
    extract_control_evidence,
)

router = APIRouter(prefix="/api/soc2", tags=["soc2"])
logger = logging.getLogger(__name__)


# ── Request / Response models ─────────────────────────────────────────────────

class ConfigFile(BaseModel):
    source: str = Field(..., description="e.g. 'iam_policies', 'cloudtrail_config', 'bucket_policies', 'cloudwatch_alarms'")
    format: str = Field(..., description="e.g. 'aws_iam_json', 'aws_cloudtrail_json'")
    content: dict = Field(..., description="Raw config content as JSON object")


class AuditIngestRequest(BaseModel):
    org_name: str = Field(..., description="Name of the organisation being audited")
    audit_id: str | None = Field(None, description="Reuse an existing audit_id or omit to generate")
    configs: list[ConfigFile] = Field(..., min_length=1, description="One or more config file objects")


class ConfigHashEntry(BaseModel):
    source: str
    format: str
    hash: str


class AuditIngestResponse(BaseModel):
    audit_id: str
    org_name: str
    corpus_root: str
    config_count: int
    config_hashes: list[ConfigHashEntry]
    control_evidence_preview: dict[str, list[str]]
    status: str


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/audits/ingest", response_model=AuditIngestResponse)
async def ingest_configs(body: AuditIngestRequest) -> AuditIngestResponse:
    """
    Ingest cloud infrastructure config files, compute their Merkle corpus root,
    and return a deterministic evidence preview per CC6/CC7 control.

    No LLM is called here — all extraction is deterministic.
    The corpus root uniquely identifies this snapshot of config evidence
    and will be embedded in the TDX report_data of the SOC2ControlCredential
    once evaluation runs (Phase 3).
    """
    audit_id = body.audit_id or str(uuid.uuid4())
    raw_configs = [c.model_dump() for c in body.configs]

    # Per-file SHA-256 hashes
    config_hashes = [
        ConfigHashEntry(
            source=c.source,
            format=c.format,
            hash=hash_config_file(c.model_dump()),
        )
        for c in body.configs
    ]

    # Merkle corpus root over all files (same algorithm as transcript hasher)
    try:
        corpus_root = compute_config_corpus_root(raw_configs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Deterministic evidence extraction — no LLM
    control_evidence = extract_control_evidence(raw_configs)

    # Persist to SQLite
    try:
        await db.create_audit(
            audit_id=audit_id,
            org_name=body.org_name,
            config_corpus_root=corpus_root,
            config_hashes_json=json.dumps([h.model_dump() for h in config_hashes]),
        )
    except Exception as exc:
        logger.error(f"Failed to persist audit {audit_id}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create audit record")

    logger.info(
        f"Audit {audit_id} ingested: org={body.org_name!r}, "
        f"files={len(body.configs)}, corpus_root={corpus_root[:16]}…"
    )

    return AuditIngestResponse(
        audit_id=audit_id,
        org_name=body.org_name,
        corpus_root=corpus_root,
        config_count=len(body.configs),
        config_hashes=config_hashes,
        control_evidence_preview=control_evidence,
        status="pending",
    )
