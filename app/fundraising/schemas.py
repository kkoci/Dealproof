"""
Fundraising diligence Pydantic schemas — Phase 1.

Phase 1: ingest request + response only.
Phase 2+: MetricsInspectionReport, FundraisingDiligenceCredential added here.
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
