"""
Fundraising metrics hasher — Phase 1.

Hashing pipeline for founder financial metrics:
  record  → hash_metrics_record()         → 64-char hex
  records → compute_metrics_corpus_root() → 64-char hex (Merkle root)
  records → extract_metric_evidence()     → structured evidence dict (no LLM)

Algorithm is identical to app/props/transcript_hasher.py so the same
length-prefixed Merkle structure is used throughout DealProof.
"""
import hashlib
import json


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def hash_metrics_record(record: dict) -> str:
    """SHA-256 of canonical JSON of one metrics record."""
    return hashlib.sha256(
        json.dumps(record, sort_keys=True).encode()
    ).hexdigest()


def compute_metrics_corpus_root(records: list[dict]) -> str:
    """
    Length-prefixed Merkle root over per-record hashes.
    Same algorithm as compute_corpus_root in transcript_hasher.py.
    """
    if not records:
        raise ValueError("compute_metrics_corpus_root requires at least one record")
    hashes = [hash_metrics_record(r) for r in records]
    length_prefix = len(hashes).to_bytes(4, "big")
    raw = length_prefix + b"".join(bytes.fromhex(h) for h in hashes)
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# Deterministic metric extraction — no LLM
# ---------------------------------------------------------------------------

def _extract_mom_growth(months: list[dict]) -> dict:
    """Average MoM revenue growth rate from a sorted monthly revenue series."""
    sorted_months = sorted(months, key=lambda m: m["month"])
    revenues = [m["revenue"] for m in sorted_months]
    if len(revenues) < 2:
        return {"values": revenues, "computed_rate": None}
    rates = [
        (revenues[i] - revenues[i - 1]) / revenues[i - 1]
        for i in range(1, len(revenues))
        if revenues[i - 1] != 0
    ]
    avg = sum(rates) / len(rates) if rates else None
    return {"values": revenues, "computed_rate": round(avg, 6) if avg is not None else None}


def _extract_gross_margin(months: list[dict]) -> dict:
    """Aggregate gross margin from monthly revenue + COGS."""
    total_revenue = sum(m.get("revenue", 0) for m in months)
    total_cogs = sum(m.get("cogs", 0) for m in months)
    if total_revenue == 0:
        return {"computed_pct": None}
    margin = (total_revenue - total_cogs) / total_revenue
    return {"computed_pct": round(margin, 6)}


def _extract_customer_concentration(customers: list[dict]) -> dict:
    """Top-customer and top-3 revenue concentration from customer breakdown."""
    if not customers:
        return {"top_customer_pct": None, "top_3_pct": None}
    total = sum(c.get("revenue", 0) for c in customers)
    if total == 0:
        return {"top_customer_pct": None, "top_3_pct": None}
    sorted_rev = sorted([c.get("revenue", 0) for c in customers], reverse=True)
    top1 = sorted_rev[0] / total
    top3 = sum(sorted_rev[:3]) / total
    return {
        "top_customer_pct": round(top1, 6),
        "top_3_pct": round(top3, 6),
    }


def _extract_burn_rate(content: dict) -> dict:
    """Runway months from monthly burn + cash balance."""
    burn = content.get("monthly_burn", 0)
    cash = content.get("cash_balance", 0)
    runway = round(cash / burn, 2) if burn > 0 else None
    return {
        "monthly_burn": burn,
        "cash_balance": cash,
        "runway_months": runway,
    }


def _extract_churn_rate(cohorts: list[dict]) -> dict:
    """
    Average monthly churn from 3-month cohort retention data.
    monthly_churn = 1 - (active_after_3mo / starting_customers)^(1/3)
    """
    if not cohorts:
        return {"computed_monthly_churn": None}
    monthly_churns = []
    for c in cohorts:
        start = c.get("starting_customers", 0)
        active = c.get("active_after_3mo", 0)
        if start > 0:
            retention_3mo = active / start
            # Compound monthly: survival^3 = retention_3mo → survival = retention_3mo^(1/3)
            monthly_survival = retention_3mo ** (1 / 3)
            monthly_churns.append(1 - monthly_survival)
    if not monthly_churns:
        return {"computed_monthly_churn": None}
    avg = sum(monthly_churns) / len(monthly_churns)
    return {"computed_monthly_churn": round(avg, 6)}


def _extract_arr_consistency(months: list[dict], reported_arr: float) -> dict:
    """
    Compare reported ARR against ARR computed from last month's revenue × 12.
    delta_pct = (reported - computed) / computed
    """
    if not months:
        return {"computed_arr": None, "reported_arr": reported_arr, "delta_pct": None}
    sorted_months = sorted(months, key=lambda m: m["month"])
    last_revenue = sorted_months[-1].get("revenue", 0)
    computed_arr = last_revenue * 12
    if computed_arr == 0:
        return {"computed_arr": 0, "reported_arr": reported_arr, "delta_pct": None}
    delta = (reported_arr - computed_arr) / computed_arr
    return {
        "computed_arr": computed_arr,
        "reported_arr": reported_arr,
        "delta_pct": round(delta, 6),
    }


def extract_metric_evidence(records: list[dict]) -> dict:
    """
    Deterministic extraction — no LLM.

    Iterates over the metrics records, identifies each by source, and
    computes structured evidence for all six metrics in scope.
    Missing sources are omitted from the output rather than raising.

    Returns:
        {
          "mom_growth": {"values": [...], "computed_rate": 0.18},
          "customer_concentration": {"top_customer_pct": 0.12, "top_3_pct": 0.31},
          "gross_margin": {"computed_pct": 0.74},
          "burn_rate": {"monthly_burn": 85000, "cash_balance": 1200000, "runway_months": 14.1},
          "churn_rate": {"computed_monthly_churn": 0.03},
          "arr_consistency": {"computed_arr": 960000, "reported_arr": 1000000, "delta_pct": 0.04}
        }
    """
    # Index records by source — last writer wins if duplicate sources
    by_source: dict[str, dict] = {}
    for r in records:
        by_source[r.get("source", "")] = r.get("content", {})

    evidence: dict = {}

    # MoM growth + gross margin share the monthly_revenue source
    revenue_content = by_source.get("monthly_revenue", {})
    months = revenue_content.get("months", [])
    if months:
        evidence["mom_growth"] = _extract_mom_growth(months)
        evidence["gross_margin"] = _extract_gross_margin(months)

    # Customer concentration
    customer_content = by_source.get("customer_revenue_breakdown", {})
    customers = customer_content.get("customers", [])
    if customers:
        evidence["customer_concentration"] = _extract_customer_concentration(customers)

    # Burn rate / runway
    if "expenses_and_cash" in by_source:
        evidence["burn_rate"] = _extract_burn_rate(by_source["expenses_and_cash"])

    # Churn rate
    cohort_content = by_source.get("cohort_retention", {})
    cohorts = cohort_content.get("cohorts", [])
    if cohorts:
        evidence["churn_rate"] = _extract_churn_rate(cohorts)

    # ARR consistency — needs both monthly_revenue and reported_arr
    if "reported_arr" in by_source and months:
        reported = by_source["reported_arr"].get("reported_arr", 0)
        evidence["arr_consistency"] = _extract_arr_consistency(months, reported)

    return evidence
