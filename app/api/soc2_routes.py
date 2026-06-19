"""
SOC 2 continuous assurance endpoints — product/continuous-soc2.

Phase 1:
  POST /api/soc2/audits/ingest          — upload config files, get corpus root + evidence preview

Phase 3:
  POST /api/soc2/audits/{audit_id}/evaluate — run full pipeline, return SOC2ControlCredential + TDX quote
  GET  /api/soc2/audits/{audit_id}          — fetch audit status and credential

The negotiation flow, πCreds logic, and agent behavior are untouched.
This router is mounted alongside the existing API under /api/soc2/.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import app.db as db
from app.soc2.config_hasher import (
    hash_config_file,
    compute_config_corpus_root,
    extract_control_evidence,
)
from app.soc2.agents.config_inspector import ConfigInspectorAgent
from app.soc2.agents.control_evaluator import ControlEvaluatorAgent
from app.soc2.schemas import ControlFinding, SOC2ControlCredential
from app.tee.attestation import sign_result

router = APIRouter(prefix="/api/soc2", tags=["soc2"])
logger = logging.getLogger(__name__)


# ── Shared request models ─────────────────────────────────────────────────────

class ConfigFile(BaseModel):
    source: str = Field(..., description="e.g. 'iam_policies', 'cloudtrail_config', 'bucket_policies', 'cloudwatch_alarms'")
    format: str = Field(..., description="e.g. 'aws_iam_json', 'aws_cloudtrail_json'")
    content: dict = Field(..., description="Raw config content as JSON object")


class ConfigHashEntry(BaseModel):
    source: str
    format: str
    hash: str


# ── Phase 1: Ingest ───────────────────────────────────────────────────────────

class AuditIngestRequest(BaseModel):
    org_name: str = Field(..., description="Name of the organisation being audited")
    audit_id: str | None = Field(None, description="Reuse an existing audit_id or omit to generate")
    configs: list[ConfigFile] = Field(..., min_length=1, description="One or more config file objects")


class AuditIngestResponse(BaseModel):
    audit_id: str
    org_name: str
    corpus_root: str
    config_count: int
    config_hashes: list[ConfigHashEntry]
    control_evidence_preview: dict[str, list[str]]
    status: str


@router.post("/audits/ingest", response_model=AuditIngestResponse)
async def ingest_configs(body: AuditIngestRequest) -> AuditIngestResponse:
    """
    Ingest cloud infrastructure config files, compute their Merkle corpus root,
    and return a deterministic evidence preview per CC6/CC7 control.
    Config content is stored so /evaluate needs no re-submission.
    """
    audit_id = body.audit_id or str(uuid.uuid4())
    raw_configs = [c.model_dump() for c in body.configs]

    config_hashes = [
        ConfigHashEntry(
            source=c.source,
            format=c.format,
            hash=hash_config_file(c.model_dump()),
        )
        for c in body.configs
    ]

    try:
        corpus_root = compute_config_corpus_root(raw_configs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    control_evidence = extract_control_evidence(raw_configs)

    try:
        await db.create_audit(
            audit_id=audit_id,
            org_name=body.org_name,
            config_corpus_root=corpus_root,
            config_hashes_json=json.dumps([h.model_dump() for h in config_hashes]),
            configs_json=json.dumps(raw_configs),
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


# ── Phase 3: Evaluate ─────────────────────────────────────────────────────────

class AuditEvaluateResponse(BaseModel):
    audit_id: str
    credential: SOC2ControlCredential
    tee_quote: str
    status: str


@router.post("/audits/{audit_id}/evaluate", response_model=AuditEvaluateResponse)
async def evaluate_audit(audit_id: str) -> AuditEvaluateResponse:
    """
    Run the full SOC 2 evaluation pipeline for a previously ingested audit:
      1. ConfigInspectorAgent  — deterministic hard boolean per control
      2. ControlEvaluatorAgent — LLM qualitative context (non-fatal if fails)
      3. Build SOC2ControlCredential + credential_hash
      4. Sign {credential_hash, corpus_root} into TDX report_data
      5. Persist and return
    """
    audit = await db.get_audit(audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    if audit["status"] == "complete":
        # Idempotent — return existing credential
        return AuditEvaluateResponse(
            audit_id=audit_id,
            credential=SOC2ControlCredential(**audit["credential"]),
            tee_quote=audit["tee_quote"] or "",
            status="complete",
        )

    configs: list[dict] = audit["configs"]
    if not configs:
        raise HTTPException(
            status_code=400,
            detail="No config data stored for this audit — re-ingest with current soc2_routes",
        )

    org_name: str = audit["org_name"]
    corpus_root: str = audit["config_corpus_root"]

    # Step 1 — deterministic hard findings
    inspector = ConfigInspectorAgent()
    hard_findings = inspector.inspect(configs)

    # Step 2 — LLM qualitative layer (non-fatal)
    evaluator = ControlEvaluatorAgent()
    evaluation = await evaluator.evaluate(org_name, configs, hard_findings)

    # Step 3 — build SOC2ControlCredential
    per_control_effective = {ctrl: r.passed for ctrl, r in hard_findings.items()}
    all_controls_effective = all(per_control_effective.values())

    control_findings = []
    for ctrl, hard_result in hard_findings.items():
        # LLM assessment for this control (if available)
        llm_assessment = ""
        llm_risk = ""
        if evaluation:
            for ca in evaluation.control_assessments:
                if ca.get("control_id") == ctrl:
                    llm_assessment = ca.get("qualitative_assessment", "")
                    llm_risk = ca.get("risk_notes", "")
                    break
        if not llm_assessment:
            llm_assessment = hard_result.finding  # fallback to hard finding text

        control_findings.append(ControlFinding(
            control_id=ctrl,
            hard_finding=hard_result.passed,
            evidence_snippets=hard_result.evidence,
            effective=hard_result.passed,           # hard finding is authoritative
            qualitative_assessment=llm_assessment,
            risk_notes=llm_risk,
        ))

    overall_assessment = (
        evaluation.overall_assessment if evaluation
        else ("All controls effective." if all_controls_effective
              else "One or more controls require remediation.")
    )
    material_weaknesses = (
        evaluation.material_weaknesses if evaluation
        else [ctrl for ctrl, passed in per_control_effective.items() if not passed]
    )
    significant_deficiencies = evaluation.significant_deficiencies if evaluation else []

    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build credential without hash first, then hash it
    credential_body = {
        "credential_type": "SOC2ControlCredential",
        "audit_id": audit_id,
        "org_name": org_name,
        "corpus_root": corpus_root,
        "controls_assessed": list(hard_findings.keys()),
        "control_findings": [cf.model_dump() for cf in control_findings],
        "overall_assessment": overall_assessment,
        "material_weaknesses": material_weaknesses,
        "significant_deficiencies": significant_deficiencies,
        "all_controls_effective": all_controls_effective,
        "issued_at": issued_at,
        "tee_attested": True,
    }
    credential_hash = hashlib.sha256(
        json.dumps(credential_body, sort_keys=True).encode()
    ).hexdigest()
    credential_body["credential_hash"] = credential_hash

    credential = SOC2ControlCredential(**credential_body)

    # Step 4 — TDX attestation: embed credential_hash + corpus_root in report_data
    tee_quote = await sign_result({
        "credential_hash": credential_hash,
        "corpus_root": corpus_root,
        "audit_id": audit_id,
        "all_controls_effective": all_controls_effective,
    })

    # Step 5 — persist
    await db.update_audit(
        audit_id=audit_id,
        status="complete",
        credential_json=json.dumps(credential_body),
        tee_quote=tee_quote,
    )

    logger.info(
        f"Audit {audit_id} evaluated: org={org_name!r}, "
        f"all_effective={all_controls_effective}, "
        f"credential_hash={credential_hash[:16]}…"
    )

    return AuditEvaluateResponse(
        audit_id=audit_id,
        credential=credential,
        tee_quote=tee_quote,
        status="complete",
    )


# ── Phase 3: Status ───────────────────────────────────────────────────────────

@router.get("/audits/{audit_id}")
async def get_audit_status(audit_id: str) -> dict:
    """Fetch audit status and credential (if evaluation is complete)."""
    audit = await db.get_audit(audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return {
        "audit_id":    audit["audit_id"],
        "org_name":    audit["org_name"],
        "corpus_root": audit["config_corpus_root"],
        "status":      audit["status"],
        "created_at":  audit["created_at"],
        "credential":  audit["credential"],
        "tee_quote":   audit["tee_quote"],
    }
