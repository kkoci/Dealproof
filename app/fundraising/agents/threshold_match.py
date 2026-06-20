"""
ThresholdMatchAgent — deterministic two-sided diligence matching (Ext-Phase 2).

No LLM. No network. Pure comparison of MetricsInspectorAgent findings against
an investor's InvestorThresholds payload.

Privacy model
─────────────
The agent computes a full internal result. Two filtered views are then derived:

  founder_view(result, disclosure)  — what the founder may learn
  investor_view(result)             — what the investor sees (never raw founder numbers)

disclosure_on_mismatch controls the founder view:
  "none"           → only overall_match bool
  "category_only"  → overall_match + list of failed metric names (not values)
  "full_threshold" → overall_match + per-metric pass/fail + investor threshold value
                     (founder still never sees their own raw value labelled as such)

The investor view always gets overall_match + per-metric pass/fail, but the
founder's computed values are never surfaced — the investor already has the
ratios-only FundraisingDiligenceCredential from the evaluate step.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.fundraising.schemas import InvestorThresholds


# ---------------------------------------------------------------------------
# Metric mapping: inspection_report field → threshold field → comparison type
# ---------------------------------------------------------------------------

# Each entry:
#   metric        unique slug used in result payloads
#   label         human-readable name shown in disclosures
#   report_key    key in the serialised MetricsInspectionReport dict
#   threshold_key attribute name on InvestorThresholds
#   direction     "gte" = founder value must be >= threshold (higher is better)
#                 "lte" = founder value must be <= threshold (lower is better)
_METRIC_MAP: list[dict] = [
    {
        "metric":        "mom_growth",
        "label":         "MoM Revenue Growth",
        "report_key":    "mom_growth_computed",
        "threshold_key": "min_mom_growth",
        "direction":     "gte",
    },
    {
        "metric":        "customer_concentration",
        "label":         "Top Customer Concentration",
        "report_key":    "top_customer_pct",
        "threshold_key": "max_customer_concentration_pct",
        "direction":     "lte",
    },
    {
        "metric":        "gross_margin",
        "label":         "Gross Margin",
        "report_key":    "gross_margin_computed",
        "threshold_key": "min_gross_margin",
        "direction":     "gte",
    },
    {
        "metric":        "runway",
        "label":         "Runway (months)",
        "report_key":    "runway_months_computed",
        "threshold_key": "min_runway_months",
        "direction":     "gte",
    },
    {
        "metric":        "monthly_churn",
        "label":         "Monthly Churn Rate",
        "report_key":    "churn_rate_computed",
        "threshold_key": "max_monthly_churn_pct",
        "direction":     "lte",
    },
    {
        "metric":        "arr_delta",
        "label":         "ARR Inconsistency Delta",
        "report_key":    "arr_delta_pct",
        "threshold_key": "max_arr_delta_pct",
        "direction":     "lte",    # absolute delta — lower is better
    },
]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MetricMatchResult:
    """Internal full result for one metric. Used to derive both views."""
    metric: str
    label: str
    investor_threshold: float | None   # None = investor didn't specify
    founder_value: float | None        # None = metric not available in inspection
    passed: bool                       # True if threshold met OR investor didn't specify


@dataclass
class ThresholdMatchResult:
    """Full internal match result. Apply founder_view() or investor_view() before returning."""
    overall_match: bool
    metric_results: list[MetricMatchResult]
    disclosure_level: str
    investor_id: str


# ---------------------------------------------------------------------------
# View helpers
# ---------------------------------------------------------------------------

def founder_view(result: ThresholdMatchResult) -> dict:
    """
    Build the founder-facing response dict, filtered per disclosure_on_mismatch.

    "none"           → {overall_match, disclosure_level}
    "category_only"  → adds failed_metrics (names only), no values
    "full_threshold" → adds per_metric_results with investor threshold; no raw founder values
    """
    base: dict = {
        "overall_match": result.overall_match,
        "disclosure_level": result.disclosure_level,
    }

    if result.disclosure_level == "none":
        return base

    # category_only and full_threshold both reveal which metrics failed
    failed_names = [
        m.label
        for m in result.metric_results
        if m.investor_threshold is not None and not m.passed
    ]

    if result.disclosure_level == "category_only":
        base["failed_metrics"] = failed_names
        base["checked_metric_count"] = sum(
            1 for m in result.metric_results if m.investor_threshold is not None
        )
        return base

    # full_threshold — reveal investor's threshold value per metric
    base["metric_results"] = [
        {
            "metric": m.metric,
            "label": m.label,
            "passed": m.passed,
            "investor_threshold": m.investor_threshold,
            # founder_value intentionally omitted — they already know their own numbers
        }
        for m in result.metric_results
        if m.investor_threshold is not None   # skip metrics investor didn't set
    ]
    return base


def investor_view(result: ThresholdMatchResult) -> dict:
    """
    Build the investor-facing response dict.

    Always includes per-metric pass/fail and the investor's own thresholds.
    Never includes the founder's raw computed values (those stay in the
    ratios-only FundraisingDiligenceCredential which the investor already holds).
    """
    return {
        "overall_match": result.overall_match,
        "disclosure_level": result.disclosure_level,
        "investor_id": result.investor_id,
        "metric_results": [
            {
                "metric": m.metric,
                "label": m.label,
                "passed": m.passed,
                "investor_threshold": m.investor_threshold,
                # founder_value never included in investor view — use the
                # FundraisingDiligenceCredential for founder ratios
            }
            for m in result.metric_results
        ],
    }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ThresholdMatchAgent:
    """
    Deterministic two-sided diligence matcher.

    Accepts the serialised MetricsInspectionReport (as produced by
    dataclasses.asdict(inspection)) and an InvestorThresholds payload.
    Returns a ThresholdMatchResult from which founder_view() and
    investor_view() can be derived.

    For arr_delta: comparison uses abs(founder_value) because the inspector
    stores a signed delta and the investor specifies a maximum absolute
    tolerance (same semantics as ARR_TOLERANCE in metrics_inspector.py).
    """

    def match(
        self,
        inspection_report: dict,
        thresholds: InvestorThresholds,
    ) -> ThresholdMatchResult:
        metric_results: list[MetricMatchResult] = []
        all_specified_passed = True

        for entry in _METRIC_MAP:
            threshold_val: float | None = getattr(thresholds, entry["threshold_key"], None)
            founder_val: float | None = inspection_report.get(entry["report_key"])

            if threshold_val is None:
                # Investor doesn't care about this metric — auto-pass
                passed = True
            elif founder_val is None:
                # Metric data unavailable in inspection — treat as fail
                passed = False
                all_specified_passed = False
            else:
                compare_val = abs(founder_val) if entry["metric"] == "arr_delta" else founder_val
                if entry["direction"] == "gte":
                    passed = compare_val >= threshold_val
                else:  # lte
                    passed = compare_val <= threshold_val

                if not passed:
                    all_specified_passed = False

            metric_results.append(MetricMatchResult(
                metric=entry["metric"],
                label=entry["label"],
                investor_threshold=threshold_val,
                founder_value=founder_val,
                passed=passed,
            ))

        return ThresholdMatchResult(
            overall_match=all_specified_passed,
            metric_results=metric_results,
            disclosure_level=thresholds.disclosure_on_mismatch,
            investor_id=thresholds.investor_id,
        )
