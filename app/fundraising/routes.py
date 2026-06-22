"""
Fundraising diligence API routes.

Original phases (unchanged):
  Phase 1: POST /api/fundraising/diligence/ingest
  Phase 3: POST /api/fundraising/diligence/{id}/evaluate
           GET  /api/fundraising/diligence/{id}

Negotiation Extension:
  Ext-Phase 1: POST /api/fundraising/diligence/{id}/investor-thresholds
  Ext-Phase 3: POST /api/fundraising/diligence/{id}/match/{threshold_id}
               GET  /api/fundraising/match/{match_id}?viewer=founder|investor
"""
import uuid
import json
import hashlib
import dataclasses
import datetime
import logging
from fastapi import APIRouter, HTTPException, Query

from app.fundraising.schemas import (
    DiligenceIngestRequest,
    DiligenceIngestResponse,
    DiligenceEvaluateRequest,
    DiligenceEvaluateResponse,
    InvestorThresholds,
    InvestorThresholdsResponse,
    FundraisingMatchCredential,
    MatchRunResponse,
    FundraisingNegotiationRequest,
    FundraisingNegotiationCredential,
)
from app.fundraising.metrics_hasher import (
    hash_metrics_record,
    compute_metrics_corpus_root,
    extract_metric_evidence,
)
from app.fundraising.agents.metrics_inspector import MetricsInspectorAgent
from app.fundraising.agents.metrics_evaluator import MetricsEvaluatorAgent, EvaluationReport
from app.fundraising.agents.threshold_match import (
    ThresholdMatchAgent,
    founder_view as _founder_view,
    investor_view as _investor_view,
)
from app.fundraising.agents.founder_agent import FounderAgent
from app.fundraising.agents.investor_agent import InvestorAgent
from app.agents.negotiation import run_negotiation
from app.tee.attestation import sign_result
from app.memory.client import search_memories, add_memories
from app.picreds.auditor import audit_fundraising_conduct
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


# ---------------------------------------------------------------------------
# Negotiation Extension — Ext-Phase 3
# ---------------------------------------------------------------------------

@router.post(
    "/diligence/{diligence_id}/match/{threshold_id}",
    response_model=MatchRunResponse,
    status_code=201,
)
async def run_match(
    diligence_id: str,
    threshold_id: str,
) -> MatchRunResponse:
    """
    Run a two-sided diligence match.

    Fetches the founder's already-computed MetricsInspectionReport and the
    investor's stored InvestorThresholds, then produces a
    FundraisingMatchCredential attested by TDX.

    The response contains two views of the result:
      founder_view  — filtered per disclosure_on_mismatch (investor's choice)
      investor_view — full pass/fail + thresholds; founder raw values never included

    Both views share the same credential_hash and TDX quote so either party
    can verify the integrity of the outcome they received.

    Requires the diligence to have been evaluated first (status == 'evaluated').
    """
    # ------------------------------------------------------------------ #
    # Step 1 — fetch founder's evaluated diligence
    # ------------------------------------------------------------------ #
    diligence_row = await db.get_diligence(diligence_id)
    if diligence_row is None:
        raise HTTPException(status_code=404, detail=f"Diligence '{diligence_id}' not found.")

    if diligence_row["status"] != "evaluated" or not diligence_row["credential"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Diligence '{diligence_id}' has not been evaluated yet. "
                "Call POST /api/fundraising/diligence/{id}/evaluate first."
            ),
        )

    corpus_root: str = diligence_row.get("corpus_root", "")
    credential = diligence_row["credential"]
    inspection_report: dict = credential.get("inspector_findings", {})
    source_diligence_credential_hash: str = credential.get("credential_hash", "")

    # ------------------------------------------------------------------ #
    # Step 2 — fetch investor thresholds
    # ------------------------------------------------------------------ #
    threshold_record = await db.get_investor_thresholds(threshold_id)
    if threshold_record is None:
        raise HTTPException(status_code=404, detail=f"Threshold record '{threshold_id}' not found.")

    if threshold_record["diligence_id"] != diligence_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Threshold '{threshold_id}' is linked to diligence "
                f"'{threshold_record['diligence_id']}', not '{diligence_id}'."
            ),
        )

    thresholds = InvestorThresholds(**threshold_record["thresholds"])

    # ------------------------------------------------------------------ #
    # Step 3 — run ThresholdMatchAgent (deterministic, no LLM)
    # ------------------------------------------------------------------ #
    agent = ThresholdMatchAgent()
    match_result = agent.match(inspection_report, thresholds)

    # Serialize the full internal result for storage (used by GET endpoint)
    match_raw = {
        "overall_match": match_result.overall_match,
        "disclosure_level": match_result.disclosure_level,
        "investor_id": match_result.investor_id,
        "metric_results": [dataclasses.asdict(m) for m in match_result.metric_results],
    }

    # ------------------------------------------------------------------ #
    # Step 4 — build FundraisingMatchCredential
    # ------------------------------------------------------------------ #
    match_id = str(uuid.uuid4())
    issued_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    inv_view = _investor_view(match_result)

    credential_fields: dict = {
        "credential_type": "FundraisingMatchCredential",
        "match_id": match_id,
        "diligence_id": diligence_id,
        "investor_id": thresholds.investor_id,
        "overall_match": match_result.overall_match,
        "metric_results": inv_view["metric_results"],
        "source_diligence_credential_hash": source_diligence_credential_hash,
        "issued_at": issued_at,
    }
    credential_hash = hashlib.sha256(
        json.dumps(credential_fields, sort_keys=True).encode()
    ).hexdigest()
    credential_fields["credential_hash"] = credential_hash

    # ------------------------------------------------------------------ #
    # Step 5 — TDX attestation
    # ------------------------------------------------------------------ #
    tee_attested = True
    tee_quote = ""
    try:
        tee_quote = await sign_result({
            "source_diligence_credential_hash": source_diligence_credential_hash,
            "match_credential_hash": credential_hash,
        })
    except Exception as exc:
        tee_attested = False
        logger.warning(
            f"Match {match_id}: TDX attestation failed (non-fatal) — "
            f"{type(exc).__name__}: {exc}"
        )

    # ------------------------------------------------------------------ #
    # Step 6 — persist
    # ------------------------------------------------------------------ #
    await db.save_match_result(
        match_id=match_id,
        diligence_id=diligence_id,
        threshold_id=threshold_id,
        investor_id=thresholds.investor_id,
        overall_match=match_result.overall_match,
        match_raw=match_raw,
        source_diligence_credential_hash=source_diligence_credential_hash,
        credential_hash=credential_hash,
        disclosure_on_mismatch=thresholds.disclosure_on_mismatch,
        tee_quote=tee_quote,
        issued_at=issued_at,
    )

    fdr_view = _founder_view(match_result)

    logger.info(
        f"Match {match_id} — diligence={diligence_id}, "
        f"investor={thresholds.investor_id}, overall_match={match_result.overall_match}, "
        f"disclosure={thresholds.disclosure_on_mismatch}, "
        f"credential_hash={credential_hash[:16]}..."
    )

    return MatchRunResponse(
        match_id=match_id,
        diligence_id=diligence_id,
        investor_id=thresholds.investor_id,
        overall_match=match_result.overall_match,
        founder_view=fdr_view,
        investor_view=inv_view,
        corpus_root=corpus_root,
        credential_hash=credential_hash,
        source_diligence_credential_hash=source_diligence_credential_hash,
        tee_quote=tee_quote,
        tee_attested=tee_attested,
    )


@router.get("/match/{match_id}", status_code=200)
async def get_match_result(
    match_id: str,
    viewer: str = Query(
        "investor",
        description=(
            "Which party's view to return: 'founder' or 'investor'. "
            # NOTE: In production this must be enforced by auth/session, not a
            # query param. Using a param here for PoC convenience — harden before
            # shipping to real users.
        ),
    ),
) -> dict:
    """
    Fetch a match result in the caller's permitted view.

    viewer=founder  — overall_match + disclosure-filtered detail
    viewer=investor — full per-metric pass/fail + investor thresholds
                      (never contains founder's raw computed values)

    Both views include the same credential_hash and tee_quote so either party
    can independently verify the integrity of the attested outcome.
    """
    if viewer not in ("founder", "investor"):
        raise HTTPException(
            status_code=422,
            detail="viewer must be 'founder' or 'investor'.",
        )

    row = await db.get_match_result(match_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Match '{match_id}' not found.")

    diligence_row = await db.get_diligence(row["diligence_id"])
    corpus_root = diligence_row.get("corpus_root", "") if diligence_row else ""

    # Reconstruct a minimal ThresholdMatchResult-like structure from stored raw data
    # so we can re-apply the view helpers consistently.
    from app.fundraising.agents.threshold_match import (
        ThresholdMatchResult,
        MetricMatchResult,
    )

    raw = row["match_raw"]
    metric_results = [
        MetricMatchResult(
            metric=m["metric"],
            label=m["label"],
            investor_threshold=m.get("investor_threshold"),
            founder_value=m.get("founder_value"),
            passed=m["passed"],
        )
        for m in raw.get("metric_results", [])
    ]
    result = ThresholdMatchResult(
        overall_match=row["overall_match"],
        metric_results=metric_results,
        disclosure_level=row["disclosure_on_mismatch"],
        investor_id=row["investor_id"],
    )

    match_view = _founder_view(result) if viewer == "founder" else _investor_view(result)

    return {
        "match_id": match_id,
        "diligence_id": row["diligence_id"],
        "viewer": viewer,
        "corpus_root": corpus_root,
        "credential_hash": row["credential_hash"],
        "source_diligence_credential_hash": row["source_diligence_credential_hash"],
        "tee_quote": row["tee_quote"],
        "issued_at": row["issued_at"],
        **match_view,
    }


# ---------------------------------------------------------------------------
# Agent Negotiation Upgrade — AN3
# ---------------------------------------------------------------------------

def _format_memories(results: list[dict]) -> str:
    if not results:
        return ""
    lines = []
    for r in results[:5]:
        content = r.get("content") or r.get("text") or str(r)
        lines.append(f"- {content}")
    return "\n".join(lines)


def _build_investor_diligence_summary(inspector_findings: dict, any_flag_raised: bool) -> str:
    """
    Build a ratios-only summary for the investor from inspector findings.
    Raw founder financial figures are never included — only computed ratios.
    """
    lines = []
    mom = inspector_findings.get("mom_growth_computed")
    if mom is not None:
        lines.append(f"  MoM Revenue Growth: {mom * 100:.1f}%")
    margin = inspector_findings.get("gross_margin_computed")
    if margin is not None:
        lines.append(f"  Gross Margin: {margin * 100:.1f}%")
    runway = inspector_findings.get("runway_months_computed")
    if runway is not None:
        lines.append(f"  Runway: {runway:.1f} months")
    churn = inspector_findings.get("churn_rate_computed")
    if churn is not None:
        lines.append(f"  Monthly Churn: {churn * 100:.2f}%")
    if any_flag_raised:
        lines.append("  [FLAGS RAISED — see FundraisingDiligenceCredential for details]")
    return "\n".join(lines) or "(no metric findings available)"


@router.post(
    "/negotiation/run",
    response_model=FundraisingNegotiationCredential,
    status_code=200,
)
async def run_fundraising_negotiation(
    payload: FundraisingNegotiationRequest,
) -> FundraisingNegotiationCredential:
    """
    Run a TEE-resident fundraising negotiation between FounderAgent + InvestorAgent.

    Requires the diligence_id to reference an *evaluated* FundraisingDiligenceCredential —
    the inspector_findings from that credential are injected into both agents as
    TEE-verified authoritative grounding.

    Flow:
      M1  Contexto memory search for founder:{diligence_id} + investor:{investor_id} (non-fatal)
      1   Build FounderAgent (with inspection_report) + InvestorAgent (with ratios-only summary)
      2   run_negotiation() — same loop as Deal Room, FounderAgent as seller, InvestorAgent as buyer
      M2  Post-deal memory write (non-fatal, only on agreement)
      P   audit_fundraising_conduct — SCAE claim consistency + qualitative (non-fatal, only on agreement)
      A   TDX attestation: SHA-256({diligence_credential_hash, negotiation_picreds_hash, final_valuation, agreed})
      4   Persist + return FundraisingNegotiationCredential

    Resilience: memory + πCreds are non-fatal; attestation always runs.
    """
    # --------------------------------------------------------------- #
    # Step 0 — validate: diligence must exist and be evaluated
    # --------------------------------------------------------------- #
    row = await db.get_diligence(payload.diligence_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Diligence '{payload.diligence_id}' not found.",
        )
    if row["status"] != "evaluated" or not row["credential"]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Diligence '{payload.diligence_id}' has not been evaluated "
                f"(status: {row['status']}). "
                "Call POST /api/fundraising/diligence/{id}/evaluate first."
            ),
        )

    credential = row["credential"]
    diligence_credential_hash: str = credential.get("credential_hash", "")
    inspector_findings: dict = credential.get("inspector_findings", {})
    any_flag_raised: bool = credential.get("any_flag_raised", False)
    company_description = f"{row['company_name']} ({row['round_label'] or 'fundraising round'})"

    negotiation_id = str(uuid.uuid4())
    issued_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # --------------------------------------------------------------- #
    # Step M1 — recall memory context for both agents (non-fatal)
    # agent IDs: founder scoped to company, investor scoped to investor
    # --------------------------------------------------------------- #
    founder_agent_id = f"founder:{payload.diligence_id}"
    investor_agent_id = f"investor:{payload.investor_id}"

    founder_memory_context = ""
    investor_memory_context = ""
    memory_context_hash: str | None = None

    try:
        founder_mems = await search_memories(
            founder_agent_id,
            f"fundraising negotiation outcomes for {row['company_name']}",
        )
        investor_mems = await search_memories(
            investor_agent_id,
            "prior investments, accepted valuations, rejection patterns",
        )
        founder_memory_context = _format_memories(founder_mems)
        investor_memory_context = _format_memories(investor_mems)
    except Exception as exc:
        logger.warning(f"Negotiation {negotiation_id}: memory search failed (non-fatal) — {exc}")

    if founder_memory_context or investor_memory_context:
        memory_context_hash = hashlib.sha256(
            json.dumps(
                {"founder": founder_memory_context, "investor": investor_memory_context},
                sort_keys=True,
            ).encode()
        ).hexdigest()

    # --------------------------------------------------------------- #
    # Step 1 — build agents
    # --------------------------------------------------------------- #
    diligence_summary = _build_investor_diligence_summary(inspector_findings, any_flag_raised)

    founder = FounderAgent(
        floor_valuation=payload.founder_floor_valuation,
        valuation_ask=payload.founder_valuation_ask,
        company_description=company_description,
        inspection_report=inspector_findings,
        memory_context=founder_memory_context,
    )
    investor = InvestorAgent(
        max_valuation=payload.investor_max_valuation,
        investment_amount=payload.investor_investment_amount,
        target_ownership_pct=payload.investor_target_ownership_pct,
        requirements=payload.investor_requirements or "",
        diligence_summary=diligence_summary,
        memory_context=investor_memory_context,
    )

    # --------------------------------------------------------------- #
    # Step 2 — negotiation loop
    # FounderAgent = seller, InvestorAgent = buyer in run_negotiation()
    # --------------------------------------------------------------- #
    result = await run_negotiation(
        buyer=investor,
        seller=founder,
        max_rounds=payload.max_rounds,
    )

    transcript_data = [
        {
            "round": r.round,
            "role": r.role,
            "action": r.action,
            "price": r.price,
            "reasoning": r.reasoning,
        }
        for r in result.transcript
    ]

    # --------------------------------------------------------------- #
    # Steps M2 / P — post-deal steps (non-fatal, only on agreement)
    # --------------------------------------------------------------- #
    memory_attested = False
    memory_write_hash: str | None = None
    conduct_audit: dict | None = None
    picreds_attested = False
    negotiation_picreds_hash: str | None = None

    if result.agreed:
        # Step M2: write deal outcome to both agent memories
        try:
            outcome_messages = [
                {
                    "role": "user",
                    "content": (
                        f"Fundraising negotiation: {company_description}. "
                        f"Investor: {payload.investor_id}."
                    ),
                },
                {
                    "role": "assistant",
                    "content": (
                        f"Agreed at pre-money valuation {result.final_price}. "
                        f"Terms: {result.terms}."
                    ),
                },
            ]
            memory_write_hash = hashlib.sha256(
                json.dumps(outcome_messages, sort_keys=True).encode()
            ).hexdigest()
            await add_memories(founder_agent_id, outcome_messages, user_id=negotiation_id)
            await add_memories(investor_agent_id, outcome_messages, user_id=negotiation_id)
            memory_attested = True
            logger.info(f"Negotiation {negotiation_id}: memories stored for both agents")
        except Exception as exc:
            logger.warning(f"Negotiation {negotiation_id}: memory store failed (non-fatal) — {exc}")

        # Step P: πCreds — audit_fundraising_conduct (non-fatal)
        try:
            conduct_audit = await audit_fundraising_conduct(
                transcript_data,
                investor_cap=payload.investor_max_valuation,
                floor_valuation=payload.founder_floor_valuation,
                final_valuation=result.final_price,
                inspection_report=inspector_findings,
            )
            negotiation_picreds_hash = hashlib.sha256(
                json.dumps(conduct_audit, sort_keys=True).encode()
            ).hexdigest()
            picreds_attested = True
            logger.info(f"Negotiation {negotiation_id}: πCreds audit complete")
        except Exception as exc:
            logger.warning(f"Negotiation {negotiation_id}: πCreds audit failed (non-fatal) — {exc}")

    # --------------------------------------------------------------- #
    # Step A — TDX attestation
    # report_data covers diligence provenance + conduct audit + outcome
    # --------------------------------------------------------------- #
    tee_quote = await sign_result({
        "diligence_credential_hash": diligence_credential_hash,
        "negotiation_picreds_hash": negotiation_picreds_hash or "",
        "final_valuation": result.final_price,
        "agreed": result.agreed,
    })

    # --------------------------------------------------------------- #
    # Step 4 — build credential_hash + persist
    # --------------------------------------------------------------- #
    credential_fields: dict = {
        "credential_type": "FundraisingNegotiationCredential",
        "negotiation_id": negotiation_id,
        "diligence_id": payload.diligence_id,
        "investor_id": payload.investor_id,
        "diligence_credential_hash": diligence_credential_hash,
        "agreed": result.agreed,
        "final_valuation": result.final_price,
        "round_count": len(result.transcript),
        "conduct_audit": conduct_audit,
        "picreds_attested": picreds_attested,
        "negotiation_picreds_hash": negotiation_picreds_hash,
        "memory_attested": memory_attested,
        "memory_context_hash": memory_context_hash,
        "memory_write_hash": memory_write_hash,
        "issued_at": issued_at,
    }
    credential_hash_value = hashlib.sha256(
        json.dumps(credential_fields, sort_keys=True).encode()
    ).hexdigest()

    await db.save_fundraising_negotiation(
        negotiation_id=negotiation_id,
        diligence_id=payload.diligence_id,
        investor_id=payload.investor_id,
        agreed=result.agreed,
        final_valuation=result.final_price,
        transcript=transcript_data,
        conduct_audit=conduct_audit,
        picreds_hash=negotiation_picreds_hash,
        memory_context_hash=memory_context_hash,
        memory_write_hash=memory_write_hash,
        diligence_credential_hash=diligence_credential_hash,
        credential_hash=credential_hash_value,
        tee_quote=tee_quote,
        issued_at=issued_at,
    )

    logger.info(
        f"Negotiation {negotiation_id} complete — "
        f"diligence={payload.diligence_id}, investor={payload.investor_id}, "
        f"agreed={result.agreed}, final_valuation={result.final_price}, "
        f"credential_hash={credential_hash_value[:16]}..."
    )

    return FundraisingNegotiationCredential(
        negotiation_id=negotiation_id,
        diligence_id=payload.diligence_id,
        investor_id=payload.investor_id,
        diligence_credential_hash=diligence_credential_hash,
        agreed=result.agreed,
        final_valuation=result.final_price,
        round_count=len(result.transcript),
        transcript=transcript_data,
        conduct_audit=conduct_audit,
        picreds_attested=picreds_attested,
        negotiation_picreds_hash=negotiation_picreds_hash,
        memory_attested=memory_attested,
        memory_context_hash=memory_context_hash,
        memory_write_hash=memory_write_hash,
        credential_hash=credential_hash_value,
        tee_quote=tee_quote,
        tee_attested=True,
        issued_at=issued_at,
    )
