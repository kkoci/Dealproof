"""
Synthetic fundraising metrics fixtures — Phase 4.

Seven scenarios with known ground-truth labels used by test_fundraising.py.
Run directly to pretty-print all scenarios as JSON (useful as demo payloads).

Scenarios
---------
clean_series_a          All six metrics favorable. Reference baseline.
customer_concentration_risk  Top customer = 45% of revenue. Inspector flags it.
runway_risk             4 months runway. Inspector flags it.
churn_risk              9% monthly churn. Inspector flags it.
arr_inflation           SCAE: reported ARR is $1.5M, computed from subscription
                        records is $960k (56% inflation). Inspector catches it.
margin_misrepresentation SCAE: founder claims 80% gross margin; COGS data
                        computes to 61%. Inspector catches the discrepancy.
mixed_signals           Good growth + margin; short runway + high concentration.
"""
import json


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

def _revenue_months(monthly_revenues: list[tuple[str, int, int]]) -> dict:
    """Build a monthly_revenue record from [(month, revenue, cogs), ...]."""
    return {
        "source": "monthly_revenue",
        "format": "revenue_timeseries_json",
        "content": {
            "months": [
                {"month": m, "revenue": r, "cogs": c}
                for m, r, c in monthly_revenues
            ]
        },
    }


def _customers(customer_revenues: list[tuple[str, int]]) -> dict:
    """Build a customer_revenue_breakdown record from [(id, revenue), ...]."""
    return {
        "source": "customer_revenue_breakdown",
        "format": "customer_breakdown_json",
        "content": {
            "customers": [
                {"customer_id": cid, "revenue": rev}
                for cid, rev in customer_revenues
            ]
        },
    }


def _cash(monthly_burn: int, cash_balance: int) -> dict:
    return {
        "source": "expenses_and_cash",
        "format": "expense_cash_json",
        "content": {"monthly_burn": monthly_burn, "cash_balance": cash_balance},
    }


def _cohorts(cohort_list: list[tuple[str, int, int]]) -> dict:
    """Build cohort_retention record from [(cohort_month, starting, active_after_3mo), ...]."""
    return {
        "source": "cohort_retention",
        "format": "cohort_json",
        "content": {
            "cohorts": [
                {"cohort_month": m, "starting_customers": s, "active_after_3mo": a}
                for m, s, a in cohort_list
            ]
        },
    }


def _arr(reported_arr: int) -> dict:
    return {
        "source": "reported_arr",
        "format": "arr_claim_json",
        "content": {"reported_arr": reported_arr},
    }


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict] = {}

# ------------------------------------------------------------------
# clean_series_a
# MoM: 78k → 84k → 92k ≈ 8.5% then 9.5% → avg ≈ 9.0%
# Gross margin: (78+84+92 - 19+20.5+22) / (78+84+92) = 193.5/254 ≈ 76.2%
# Top customer: 11k / (11+9.5+8+7+6.5+5) = 11/47 ≈ 23.4%
# Runway: 1_200_000 / 85_000 ≈ 14.1 months
# Churn: cohort 40 → 37 in 3 months → monthly survival = (37/40)^(1/3) ≈ 0.9749 → churn ≈ 2.5%
# ARR: last month 92k × 12 = 1_104_000; reported 1_100_000 → delta ≈ -0.36% (< 10%)
# ------------------------------------------------------------------
SCENARIOS["clean_series_a"] = {
    "company_name": "Acme Software Inc",
    "round_label": "Series A",
    "metrics_records": [
        _revenue_months([
            ("2025-10", 78_000, 19_000),
            ("2025-11", 84_000, 20_500),
            ("2025-12", 92_000, 22_000),
        ]),
        _customers([
            ("cust_001", 11_000),
            ("cust_002", 9_500),
            ("cust_003", 8_000),
            ("cust_004", 7_000),
            ("cust_005", 6_500),
            ("cust_006", 5_000),
        ]),
        _cash(85_000, 1_200_000),
        _cohorts([("2025-09", 40, 37)]),
        _arr(1_100_000),
    ],
    "claimed_values": {"mom_growth_rate": 0.09, "gross_margin_pct": 0.76},
    "expected": {
        "customer_concentration_flag": False,
        "runway_flag": False,
        "churn_flag": False,
        "mom_growth_verified": True,
        "gross_margin_verified": True,
        "arr_consistency_verified": True,
        "any_flag_raised": False,
    },
}

# ------------------------------------------------------------------
# customer_concentration_risk
# One customer = 45k out of 100k total revenue → 45%
# ------------------------------------------------------------------
SCENARIOS["customer_concentration_risk"] = {
    "company_name": "ConcentratedCo Ltd",
    "round_label": "Series A",
    "metrics_records": [
        _revenue_months([
            ("2025-10", 82_000, 20_000),
            ("2025-11", 90_000, 22_000),
            ("2025-12", 100_000, 24_000),
        ]),
        _customers([
            ("cust_bigone", 45_000),   # 45% → flag
            ("cust_002", 20_000),
            ("cust_003", 15_000),
            ("cust_004", 12_000),
            ("cust_005", 8_000),
        ]),
        _cash(90_000, 1_400_000),
        _cohorts([("2025-09", 50, 47)]),
        _arr(1_200_000),
    ],
    "claimed_values": {"mom_growth_rate": 0.10, "gross_margin_pct": 0.76},
    "expected": {
        "customer_concentration_flag": True,
        "runway_flag": False,
        "churn_flag": False,
        "any_flag_raised": True,
    },
}

# ------------------------------------------------------------------
# runway_risk
# 4 months runway: cash_balance = 340_000, burn = 85_000
# ------------------------------------------------------------------
SCENARIOS["runway_risk"] = {
    "company_name": "LowRunway AI",
    "round_label": "Seed",
    "metrics_records": [
        _revenue_months([
            ("2025-10", 30_000, 8_000),
            ("2025-11", 33_000, 8_500),
            ("2025-12", 36_000, 9_000),
        ]),
        _customers([
            ("cust_001", 12_000),
            ("cust_002", 10_000),
            ("cust_003", 8_000),
        ]),
        _cash(85_000, 340_000),   # 4 months → flag
        _cohorts([("2025-09", 30, 28)]),
        _arr(432_000),
    ],
    "claimed_values": {"mom_growth_rate": 0.10, "gross_margin_pct": 0.75},
    "expected": {
        "runway_flag": True,
        "customer_concentration_flag": False,
        "churn_flag": False,
        "any_flag_raised": True,
    },
}

# ------------------------------------------------------------------
# churn_risk
# cohort 100 → 73 after 3 months → survival^3 = 0.73 → survival ≈ 0.9004
# → monthly_churn ≈ 9.96% > 5% threshold
# ------------------------------------------------------------------
SCENARIOS["churn_risk"] = {
    "company_name": "ChurnWarning SaaS",
    "round_label": "Series A",
    "metrics_records": [
        _revenue_months([
            ("2025-10", 60_000, 14_000),
            ("2025-11", 65_000, 15_000),
            ("2025-12", 70_000, 16_500),
        ]),
        _customers([
            ("cust_001", 20_000),
            ("cust_002", 18_000),
            ("cust_003", 15_000),
        ]),
        _cash(75_000, 1_000_000),
        _cohorts([("2025-09", 100, 73)]),   # ≈10% monthly churn → flag
        _arr(840_000),
    ],
    "claimed_values": {"mom_growth_rate": 0.08, "gross_margin_pct": 0.77},
    "expected": {
        "churn_flag": True,
        "runway_flag": False,
        "customer_concentration_flag": False,
        "any_flag_raised": True,
    },
}

# ------------------------------------------------------------------
# arr_inflation (SCAE)
# Last month revenue = 80_000 → computed ARR = 960_000
# Reported ARR = 1_500_000 → delta = (1.5M - 960k) / 960k ≈ +56.25% → flag
# ------------------------------------------------------------------
SCENARIOS["arr_inflation"] = {
    "company_name": "ARRInfl Corp",
    "round_label": "Series B",
    "metrics_records": [
        _revenue_months([
            ("2025-10", 72_000, 17_000),
            ("2025-11", 76_000, 18_000),
            ("2025-12", 80_000, 19_000),   # last month → ARR = 80k×12 = 960k
        ]),
        _customers([
            ("cust_001", 25_000),
            ("cust_002", 20_000),
            ("cust_003", 18_000),
        ]),
        _cash(90_000, 1_350_000),
        _cohorts([("2025-09", 60, 57)]),
        _arr(1_500_000),   # SCAE: 56% above computed — should flag
    ],
    "claimed_values": {"mom_growth_rate": 0.055, "gross_margin_pct": 0.76},
    "expected": {
        "arr_consistency_verified": False,    # delta > ARR_TOLERANCE (10%)
        "any_flag_raised": True,
    },
}

# ------------------------------------------------------------------
# margin_misrepresentation (SCAE)
# Revenue = 100k, COGS = 39k → computed margin = 61%
# Claimed gross_margin_pct = 0.80 → |0.61 - 0.80| = 0.19 > 0.05 → flag
# ------------------------------------------------------------------
SCENARIOS["margin_misrepresentation"] = {
    "company_name": "MarginFudge Inc",
    "round_label": "Series A",
    "metrics_records": [
        _revenue_months([
            ("2025-10", 90_000, 35_100),    # margin = (90k-35.1k)/90k ≈ 61%
            ("2025-11", 95_000, 37_050),
            ("2025-12", 100_000, 39_000),
        ]),
        _customers([
            ("cust_001", 30_000),
            ("cust_002", 25_000),
            ("cust_003", 20_000),
        ]),
        _cash(80_000, 1_200_000),
        _cohorts([("2025-09", 50, 47)]),
        _arr(1_200_000),
    ],
    "claimed_values": {
        "mom_growth_rate": 0.054,
        "gross_margin_pct": 0.80,    # SCAE: claimed 80%, actual ≈ 61%
    },
    "expected": {
        "gross_margin_verified": False,      # |0.61 - 0.80| > CLAIM_TOLERANCE (5%)
        "any_flag_raised": True,
    },
}

# ------------------------------------------------------------------
# mixed_signals
# Good growth + margin; short runway (4.7 mo) + high concentration (38%)
# ------------------------------------------------------------------
SCENARIOS["mixed_signals"] = {
    "company_name": "MixedBag Technologies",
    "round_label": "Series A",
    "metrics_records": [
        _revenue_months([
            ("2025-10", 110_000, 27_000),
            ("2025-11", 122_000, 29_500),
            ("2025-12", 136_000, 33_000),
        ]),
        _customers([
            ("cust_bigone", 51_680),   # 38% of 136k → flag
            ("cust_002", 30_000),
            ("cust_003", 25_000),
            ("cust_004", 20_000),
            ("cust_005", 9_320),
        ]),
        _cash(100_000, 470_000),   # 4.7 months → flag
        _cohorts([("2025-09", 60, 57)]),
        _arr(1_632_000),
    ],
    "claimed_values": {"mom_growth_rate": 0.11, "gross_margin_pct": 0.757},
    "expected": {
        "customer_concentration_flag": True,
        "runway_flag": True,
        "churn_flag": False,
        "mom_growth_verified": True,
        "any_flag_raised": True,
    },
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else None
    if name:
        if name not in SCENARIOS:
            print(f"Unknown scenario '{name}'. Available: {list(SCENARIOS)}")
            sys.exit(1)
        s = SCENARIOS[name].copy()
        s.pop("claimed_values", None)
        s.pop("expected", None)
        print(json.dumps(s, indent=2))
    else:
        for scenario_name, scenario in SCENARIOS.items():
            s = scenario.copy()
            s.pop("claimed_values", None)
            s.pop("expected", None)
            print(f"\n{'='*60}")
            print(f"Scenario: {scenario_name}")
            print('='*60)
            print(json.dumps(s, indent=2))
