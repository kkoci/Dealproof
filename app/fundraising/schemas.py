"""
Fundraising diligence Pydantic schemas — Phase 1 + Phase 3.

Phase 1: ingest request + response.
Phase 3: evaluate request + FundraisingDiligenceCredential + evaluate response.
"""
from typing import Any
from pydantic import BaseModel, Field


class MetricsRecord(BaseModel):
    """One source of financial metrics data (e.g. monthly revenue, customer breakdown)."""
    source: str = Field(..., description=(
        "Identifies the data source. Recognised values: "
        "'monthly_revenue', 'customer_revenue_breakdown', "
        "'expenses_and_cash', 'cohort_retention', 'reported_arr'."
    ))
    format: str = Field(..., description="Schema variant — e.g. 'revenue_timeseries_json'.")
    content: dict[str, Any] = Field(..., description="Structured financial data for this source.")


class DiligenceIngestRequest(BaseModel):
    """Request body for POST /api/fundraising/diligence/ingest."""
    company_name: str = Field(..., min_length=1)
    round_label: str | None = Field(None, description="Free-text round label, e.g. 'Series A'.")
    diligence_id: str | None = Field(None, description="Caller-supplied UUID. Generated if omitted.")
    metrics_records: list[MetricsRecord] = Field(..., min_length=1)


class DiligenceIngestResponse(BaseModel):
    """Response from POST /api/fundraising/diligence/ingest."""
    diligence_id: str
    company_name: str
    round_label: str | None
    corpus_root: str               # Merkle root over all records — use as data_hash in deals
    record_hashes: list[str]       # per-record SHA-256 in submission order
    metric_evidence_preview: dict  # deterministic extraction — no LLM


class DiligenceEvaluateRequest(BaseModel):
    """
    Request body for POST /api/fundraising/diligence/{id}/evaluate.

    claimed_values is optional. When provided, the inspector checks computed
    metrics against founder-reported figures within CLAIM_TOLERANCE (±5%).
    When absent, only threshold flags are applied.

    claimed_values shape (all fields optional):
      {
        "mom_growth_rate": 0.18,   # claimed MoM growth (decimal)
        "gross_margin_pct": 0.74,  # claimed gross margin (decimal)
      }
    """
    claimed_values: dict[str, float] | None = Field(
        None,
        description="Founder-reported metric values for tolerance verification.",
    )


class FundraisingDiligenceCredential(BaseModel):
    """
    TEE-attested diligence credential produced by the evaluate endpoint.

    credential_hash = SHA-256(canonical JSON of the other fields).
    tee_quote = TDX quote with report_data = SHA-256(corpus_root + credential_hash + any_flag_raised).
    """
    diligence_id: str
    company_name: str
    round_label: str | None
    corpus_root: str              # links back to ingested data package
    inspector_findings: dict      # MetricsInspectionReport serialised — hard findings, authoritative
    evaluation: dict | None       # EvaluationReport serialised — LLM qualitative layer; null on failure
    any_flag_raised: bool         # authoritative roll-up from inspector (not LLM)
    credential_hash: str          # SHA-256(canonical fields above) — embedded in TDX report_data


class DiligenceEvaluateResponse(BaseModel):
    """Response from POST /api/fundraising/diligence/{id}/evaluate."""
    diligence_id: str
    company_name: str
    round_label: str | None
    corpus_root: str
    credential_hash: str
    any_flag_raised: bool
    inspector_findings: dict
    evaluation: dict | None       # null when MetricsEvaluatorAgent failed
    tee_quote: str                # TDX quote covering corpus_root + credential_hash
    evaluator_available: bool     # false when LLM evaluator was skipped/failed
