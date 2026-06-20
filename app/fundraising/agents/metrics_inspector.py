"""
MetricsInspectorAgent — deterministic hard-finding layer (Phase 2).

Runs before MetricsEvaluatorAgent. No LLM, no network.
Computes one boolean + one scalar per metric from metric_evidence.
Hard findings are authoritative — the LLM evaluator receives them as
grounding and cannot contradict them.

Mirrors the πCreds constraints.py two-layer pattern:
  deterministic inspector → LLM evaluator
  hard booleans override anything the LLM says
"""
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Thresholds — named constants, never magic numbers
# ---------------------------------------------------------------------------

CLAIM_TOLERANCE = 0.05           # ±5% — computed value vs claimed value
CONCENTRATION_FLAG_PCT = 0.30    # flag if any single customer ≥ 30% of revenue
RUNWAY_FLAG_MONTHS = 6.0         # flag if runway < 6 months
CHURN_FLAG_MONTHLY = 0.05        # flag if monthly churn > 5%
ARR_TOLERANCE = 0.10             # ±10% — computed ARR vs reported ARR


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class MetricsInspectionReport:
    # MoM growth
    mom_growth_computed: float | None
    mom_growth_verified: bool          # computed rate within CLAIM_TOLERANCE of claimed

    # Customer concentration
    top_customer_pct: float | None
    customer_concentration_flag: bool  # True if any single customer ≥ CONCENTRATION_FLAG_PCT

    # Gross margin
    gross_margin_computed: float | None
    gross_margin_verified: bool        # computed margin within CLAIM_TOLERANCE of claimed

    # Burn rate / runway
    runway_months_computed: float | None
    runway_flag: bool                  # True if runway < RUNWAY_FLAG_MONTHS

    # Churn rate
    churn_rate_computed: float | None
    churn_flag: bool                   # True if monthly churn > CHURN_FLAG_MONTHLY

    # ARR consistency
    arr_delta_pct: float | None
    arr_consistency_verified: bool     # computed ARR within ARR_TOLERANCE of reported

    # Roll-up
    any_flag_raised: bool              # True if any flag or failed verification


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class MetricsInspectorAgent:
    """
    Deterministic layer. No LLM. Runs first.

    Accepts metric_evidence (output of extract_metric_evidence) and
    claimed_values (founder-reported figures for tolerance checks).
    claimed_values is optional — when absent, verification checks are
    skipped and only flag checks run.

    claimed_values shape:
    {
      "mom_growth_rate": 0.18,      # claimed MoM growth (decimal)
      "gross_margin_pct": 0.74,     # claimed gross margin (decimal)
    }
    ARR consistency is always verified against the reported_arr embedded
    in metric_evidence["arr_consistency"]["reported_arr"] — no separate
    claim needed.
    """

    def inspect(
        self,
        metric_evidence: dict,
        claimed_values: dict | None = None,
    ) -> MetricsInspectionReport:
        claimed = claimed_values or {}

        # ------------------------------------------------------------------ #
        # MoM growth
        # ------------------------------------------------------------------ #
        mom = metric_evidence.get("mom_growth", {})
        mom_computed = mom.get("computed_rate")
        claimed_mom = claimed.get("mom_growth_rate")
        if mom_computed is not None and claimed_mom is not None:
            mom_verified = abs(mom_computed - claimed_mom) <= CLAIM_TOLERANCE
        else:
            mom_verified = True  # no claim to check against

        # ------------------------------------------------------------------ #
        # Customer concentration
        # ------------------------------------------------------------------ #
        conc = metric_evidence.get("customer_concentration", {})
        top_pct = conc.get("top_customer_pct")
        conc_flag = (top_pct is not None and top_pct >= CONCENTRATION_FLAG_PCT)

        # ------------------------------------------------------------------ #
        # Gross margin
        # ------------------------------------------------------------------ #
        gm = metric_evidence.get("gross_margin", {})
        gm_computed = gm.get("computed_pct")
        claimed_gm = claimed.get("gross_margin_pct")
        if gm_computed is not None and claimed_gm is not None:
            gm_verified = abs(gm_computed - claimed_gm) <= CLAIM_TOLERANCE
        else:
            gm_verified = True  # no claim to check against

        # ------------------------------------------------------------------ #
        # Burn rate / runway
        # ------------------------------------------------------------------ #
        burn = metric_evidence.get("burn_rate", {})
        runway = burn.get("runway_months")
        runway_flag = (runway is not None and runway < RUNWAY_FLAG_MONTHS)

        # ------------------------------------------------------------------ #
        # Churn rate
        # ------------------------------------------------------------------ #
        churn = metric_evidence.get("churn_rate", {})
        churn_computed = churn.get("computed_monthly_churn")
        churn_flag = (churn_computed is not None and churn_computed > CHURN_FLAG_MONTHLY)

        # ------------------------------------------------------------------ #
        # ARR consistency
        # ------------------------------------------------------------------ #
        arr = metric_evidence.get("arr_consistency", {})
        arr_delta = arr.get("delta_pct")
        if arr_delta is not None:
            arr_verified = abs(arr_delta) <= ARR_TOLERANCE
        else:
            arr_verified = True  # metric not present — nothing to flag

        # ------------------------------------------------------------------ #
        # Roll-up: any flag or failed verification
        # ------------------------------------------------------------------ #
        any_flag = (
            conc_flag
            or runway_flag
            or churn_flag
            or not mom_verified
            or not gm_verified
            or not arr_verified
        )

        return MetricsInspectionReport(
            mom_growth_computed=mom_computed,
            mom_growth_verified=mom_verified,
            top_customer_pct=top_pct,
            customer_concentration_flag=conc_flag,
            gross_margin_computed=gm_computed,
            gross_margin_verified=gm_verified,
            runway_months_computed=runway,
            runway_flag=runway_flag,
            churn_rate_computed=churn_computed,
            churn_flag=churn_flag,
            arr_delta_pct=arr_delta,
            arr_consistency_verified=arr_verified,
            any_flag_raised=any_flag,
        )
