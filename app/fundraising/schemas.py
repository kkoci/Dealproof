"""
Fundraising diligence Pydantic schemas.

Original phases:
  Phase 1: ingest request + response.
  Phase 3: evaluate request + FundraisingDiligenceCredential + evaluate response.

Negotiation Extension:
  Ext-Phase 1: InvestorThresholds + InvestorThresholdsResponse.
  Ext-Phase 3: FundraisingMatchCredential + match endpoint schemas.
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


# ---------------------------------------------------------------------------
# Negotiation Extension — Ext-Phase 1
# ---------------------------------------------------------------------------

class InvestorThresholds(BaseModel):
    """
    An investor's private diligence requirements for a given round.
    Mirrors the six metrics computed by MetricsInspectorAgent so that
    ThresholdMatchAgent can do a direct field-by-field comparison.

    All threshold fields are optional — None means the investor doesn't
    require that metric to pass a specific bar.

    disclosure_on_mismatch controls what the *founder* learns when a
    threshold isn't met:
      "none"           — founder sees only overall_match bool
      "category_only"  — founder sees which metric names failed (default)
      "full_threshold" — founder sees the investor's exact threshold value
    """
    investor_id: str = Field(..., description="Opaque investor identifier — no PII required.")
    min_mom_growth: float | None = Field(
        None, description="Minimum acceptable MoM growth rate (decimal, e.g. 0.10 = 10%)."
    )
    max_customer_concentration_pct: float | None = Field(
        None, description="Maximum acceptable top-customer revenue concentration (0–1)."
    )
    min_gross_margin: float | None = Field(
        None, description="Minimum acceptable gross margin (decimal, e.g. 0.60 = 60%)."
    )
    min_runway_months: float | None = Field(
        None, description="Minimum acceptable months of runway."
    )
    max_monthly_churn_pct: float | None = Field(
        None, description="Maximum acceptable monthly churn rate (decimal, e.g. 0.03 = 3%)."
    )
    max_arr_delta_pct: float | None = Field(
        None, description="Maximum acceptable ARR inconsistency delta (decimal, e.g. 0.10 = 10%)."
    )
    disclosure_on_mismatch: str = Field(
        "category_only",
        description=(
            "How much detail the founder receives on threshold failures. "
            "One of: 'none', 'category_only', 'full_threshold'."
        ),
    )


class InvestorThresholdsResponse(BaseModel):
    """Response from POST /api/fundraising/diligence/{id}/investor-thresholds."""
    threshold_id: str
    diligence_id: str
    investor_id: str
    disclosure_on_mismatch: str
    created_at: str


# ---------------------------------------------------------------------------
# Negotiation Extension — Ext-Phase 3
# ---------------------------------------------------------------------------

class FundraisingMatchCredential(BaseModel):
    """
    TEE-attested two-sided match credential.

    Produced by POST /api/fundraising/diligence/{id}/match/{threshold_id}.

    metric_results shape varies by disclosure_on_mismatch — see
    ThresholdMatchAgent.founder_view() / investor_view() for exact shape.

    credential_hash = SHA-256(canonical JSON of all fields above it, sort_keys=True).
    TDX report_data = SHA-256({source_diligence_credential_hash, match_credential_hash}).
    """
    credential_type: str = "FundraisingMatchCredential"
    match_id: str
    diligence_id: str
    investor_id: str
    overall_match: bool
    metric_results: list[dict]              # shaped per investor_view (pass/fail + thresholds)
    source_diligence_credential_hash: str   # hash of the FundraisingDiligenceCredential matched against
    credential_hash: str
    issued_at: str
    tee_attested: bool


# ---------------------------------------------------------------------------
# Agent Negotiation Upgrade — AN3
# ---------------------------------------------------------------------------

class FundraisingNegotiationRequest(BaseModel):
    """
    Request body for POST /api/fundraising/negotiation/run.

    diligence_id must reference an *evaluated* FundraisingDiligenceCredential.
    The inspector_findings from that credential are injected into both agents
    as TEE-verified authoritative grounding.

    investor_max_valuation = budget ceiling (maps to buyer.budget in run_negotiation).
    founder_floor_valuation = minimum acceptable (maps to seller.floor_price in run_negotiation).
    """
    diligence_id: str = Field(..., description="Evaluated diligence record to negotiate over.")
    investor_id: str = Field(..., description="Opaque investor identifier.")
    investor_max_valuation: float = Field(..., gt=0, description="Hard cap on pre-money valuation.")
    investor_investment_amount: float = Field(..., gt=0, description="Capital to deploy.")
    investor_target_ownership_pct: float = Field(..., gt=0, le=100, description="Target equity % (e.g. 15.0).")
    investor_requirements: str | None = Field(None, description="Investment thesis / deal requirements.")
    founder_floor_valuation: float = Field(..., gt=0, description="Minimum acceptable pre-money valuation.")
    founder_valuation_ask: float = Field(..., gt=0, description="Opening pre-money valuation ask.")
    max_rounds: int = Field(8, ge=1, le=20, description="Maximum negotiation rounds before deadlock.")


class FundraisingNegotiationCredential(BaseModel):
    """
    TEE-attested fundraising negotiation credential.

    Produced by POST /api/fundraising/negotiation/run.

    tee_quote report_data = SHA-256({diligence_credential_hash, negotiation_picreds_hash,
                                     final_valuation, agreed}).
    credential_hash = SHA-256(all fields except credential_hash and tee_quote, sort_keys=True).
    """
    credential_type: str = "FundraisingNegotiationCredential"
    negotiation_id: str
    diligence_id: str
    investor_id: str
    diligence_credential_hash: str      # links this negotiation to its diligence credential
    agreed: bool
    final_valuation: float | None       # None when no agreement reached
    round_count: int
    transcript: list[dict]
    conduct_audit: dict | None          # from audit_fundraising_conduct; None on failure
    picreds_attested: bool              # True when conduct_audit succeeded
    negotiation_picreds_hash: str | None  # SHA-256(conduct_audit, sort_keys=True)
    memory_attested: bool               # True when post-deal memory write succeeded
    memory_context_hash: str | None     # SHA-256 of recalled memories injected into prompts
    memory_write_hash: str | None       # SHA-256 of outcome messages written to memory
    credential_hash: str                # SHA-256(all fields above, sort_keys=True)
    tee_quote: str                      # TDX quote; report_data covers diligence + picreds hashes
    tee_attested: bool
    issued_at: str


class MatchRunResponse(BaseModel):
    """Response from POST /api/fundraising/diligence/{id}/match/{threshold_id}."""
    match_id: str
    diligence_id: str
    investor_id: str
    overall_match: bool
    founder_view: dict      # filtered per disclosure_on_mismatch
    investor_view: dict     # full pass/fail + thresholds, no founder raw values
    corpus_root: str
    credential_hash: str
    source_diligence_credential_hash: str
    tee_quote: str
    tee_attested: bool
