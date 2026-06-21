# Fundraising Payloads — Exhaustive Reference

All endpoints, all scenarios, all disclosure modes. Use against `http://localhost:8000`.
Swagger UI: `http://localhost:8000/docs`

---

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/fundraising/diligence/ingest` | Ingest founder metrics → corpus root |
| `GET` | `/api/fundraising/diligence/{diligence_id}` | Fetch diligence record |
| `POST` | `/api/fundraising/diligence/{diligence_id}/evaluate` | Run inspector + LLM evaluator |
| `POST` | `/api/fundraising/diligence/{diligence_id}/investor-thresholds` | Submit investor thresholds |
| `POST` | `/api/fundraising/diligence/{diligence_id}/match/{threshold_id}` | Run match credential |
| `GET` | `/api/fundraising/match/{match_id}?viewer=founder\|investor` | Fetch match result |
| `POST` | `/api/fundraising/negotiation/run` | Run FounderAgent vs InvestorAgent negotiation |

---

## Flag Thresholds (MetricsInspectorAgent)

| Metric | Flag condition |
|--------|---------------|
| Customer concentration | top customer ≥ 30% of revenue |
| Runway | < 12 months |
| Monthly churn | > 5% |
| Claimed vs computed tolerance | > ±5% discrepancy |
| ARR consistency | > ±10% discrepancy vs computed |

---

## Full End-to-End Flow

```
1. POST /api/fundraising/diligence/ingest
       → diligence_id, corpus_root

2. POST /api/fundraising/diligence/{diligence_id}/evaluate
       → inspector_findings, credential_hash, any_flag_raised

3. POST /api/fundraising/diligence/{diligence_id}/investor-thresholds
       → threshold_id

4. POST /api/fundraising/diligence/{diligence_id}/match/{threshold_id}
       → overall_match, founder_view, investor_view, credential_hash

5. POST /api/fundraising/negotiation/run          (uses diligence_id from step 1)
       → agreed, final_valuation, transcript, credential_hash
```

---

## Step 1 — Ingest (7 Scenarios)

### Scenario 1: Clean Series A (baseline — no flags)

All metrics favorable. Expected: `any_flag_raised: false`.
MoM growth ~9%, gross margin ~76%, runway 14.1 mo, churn 2.5%, ARR delta ~-0.4%.

```json
{
  "company_name": "Acme Software Inc",
  "round_label": "Series A",
  "metrics_records": [
    {
      "source": "monthly_revenue",
      "format": "revenue_timeseries_json",
      "content": {
        "months": [
          {"month": "2025-10", "revenue": 78000, "cogs": 19000},
          {"month": "2025-11", "revenue": 84000, "cogs": 20500},
          {"month": "2025-12", "revenue": 92000, "cogs": 22000}
        ]
      }
    },
    {
      "source": "customer_revenue_breakdown",
      "format": "customer_breakdown_json",
      "content": {
        "customers": [
          {"customer_id": "cust_001", "revenue": 11000},
          {"customer_id": "cust_002", "revenue": 9500},
          {"customer_id": "cust_003", "revenue": 8000},
          {"customer_id": "cust_004", "revenue": 7000},
          {"customer_id": "cust_005", "revenue": 6500},
          {"customer_id": "cust_006", "revenue": 5000}
        ]
      }
    },
    {
      "source": "expenses_and_cash",
      "format": "expense_cash_json",
      "content": {
        "monthly_burn": 85000,
        "cash_balance": 1200000
      }
    },
    {
      "source": "cohort_retention",
      "format": "cohort_json",
      "content": {
        "cohorts": [
          {"cohort_month": "2025-09", "starting_customers": 40, "active_after_3mo": 37}
        ]
      }
    },
    {
      "source": "reported_arr",
      "format": "arr_claim_json",
      "content": {"reported_arr": 1100000}
    }
  ]
}
```

---

### Scenario 2: Customer Concentration Risk (flag)

Top customer is 45% of revenue. Expected: `customer_concentration_flag: true`.

```json
{
  "company_name": "ConcentratedCo",
  "round_label": "Series A",
  "metrics_records": [
    {
      "source": "monthly_revenue",
      "format": "revenue_timeseries_json",
      "content": {
        "months": [
          {"month": "2025-10", "revenue": 78000, "cogs": 19000},
          {"month": "2025-11", "revenue": 84000, "cogs": 20500},
          {"month": "2025-12", "revenue": 92000, "cogs": 22000}
        ]
      }
    },
    {
      "source": "customer_revenue_breakdown",
      "format": "customer_breakdown_json",
      "content": {
        "customers": [
          {"customer_id": "cust_001", "revenue": 41400},
          {"customer_id": "cust_002", "revenue": 18400},
          {"customer_id": "cust_003", "revenue": 15000},
          {"customer_id": "cust_004", "revenue": 9200},
          {"customer_id": "cust_005", "revenue": 8000}
        ]
      }
    },
    {
      "source": "expenses_and_cash",
      "format": "expense_cash_json",
      "content": {"monthly_burn": 85000, "cash_balance": 1200000}
    },
    {
      "source": "cohort_retention",
      "format": "cohort_json",
      "content": {
        "cohorts": [
          {"cohort_month": "2025-09", "starting_customers": 40, "active_after_3mo": 37}
        ]
      }
    },
    {
      "source": "reported_arr",
      "format": "arr_claim_json",
      "content": {"reported_arr": 1100000}
    }
  ]
}
```

---

### Scenario 3: Runway Risk (flag)

4 months runway. Expected: `runway_flag: true`.

```json
{
  "company_name": "LowRunwayCo",
  "round_label": "Seed Extension",
  "metrics_records": [
    {
      "source": "monthly_revenue",
      "format": "revenue_timeseries_json",
      "content": {
        "months": [
          {"month": "2025-10", "revenue": 78000, "cogs": 19000},
          {"month": "2025-11", "revenue": 84000, "cogs": 20500},
          {"month": "2025-12", "revenue": 92000, "cogs": 22000}
        ]
      }
    },
    {
      "source": "customer_revenue_breakdown",
      "format": "customer_breakdown_json",
      "content": {
        "customers": [
          {"customer_id": "cust_001", "revenue": 11000},
          {"customer_id": "cust_002", "revenue": 9500},
          {"customer_id": "cust_003", "revenue": 8000},
          {"customer_id": "cust_004", "revenue": 7000},
          {"customer_id": "cust_005", "revenue": 6500}
        ]
      }
    },
    {
      "source": "expenses_and_cash",
      "format": "expense_cash_json",
      "content": {"monthly_burn": 85000, "cash_balance": 340000}
    },
    {
      "source": "cohort_retention",
      "format": "cohort_json",
      "content": {
        "cohorts": [
          {"cohort_month": "2025-09", "starting_customers": 40, "active_after_3mo": 37}
        ]
      }
    },
    {
      "source": "reported_arr",
      "format": "arr_claim_json",
      "content": {"reported_arr": 1100000}
    }
  ]
}
```

---

### Scenario 4: High Monthly Churn (flag)

~10% monthly churn. Expected: `churn_flag: true`.

```json
{
  "company_name": "ChurnyCo",
  "round_label": "Series A",
  "metrics_records": [
    {
      "source": "monthly_revenue",
      "format": "revenue_timeseries_json",
      "content": {
        "months": [
          {"month": "2025-10", "revenue": 78000, "cogs": 19000},
          {"month": "2025-11", "revenue": 84000, "cogs": 20500},
          {"month": "2025-12", "revenue": 92000, "cogs": 22000}
        ]
      }
    },
    {
      "source": "customer_revenue_breakdown",
      "format": "customer_breakdown_json",
      "content": {
        "customers": [
          {"customer_id": "cust_001", "revenue": 11000},
          {"customer_id": "cust_002", "revenue": 9500},
          {"customer_id": "cust_003", "revenue": 8000},
          {"customer_id": "cust_004", "revenue": 7000},
          {"customer_id": "cust_005", "revenue": 6500}
        ]
      }
    },
    {
      "source": "expenses_and_cash",
      "format": "expense_cash_json",
      "content": {"monthly_burn": 85000, "cash_balance": 1200000}
    },
    {
      "source": "cohort_retention",
      "format": "cohort_json",
      "content": {
        "cohorts": [
          {"cohort_month": "2025-09", "starting_customers": 100, "active_after_3mo": 72}
        ]
      }
    },
    {
      "source": "reported_arr",
      "format": "arr_claim_json",
      "content": {"reported_arr": 1100000}
    }
  ]
}
```

---

### Scenario 5: ARR Inflation — SCAE (flag)

Reported $1.5M ARR, computed ~$960k. 56% inflation.
Expected: `arr_consistency_verified: false`.

```json
{
  "company_name": "InflatedARRCo",
  "round_label": "Series A",
  "metrics_records": [
    {
      "source": "monthly_revenue",
      "format": "revenue_timeseries_json",
      "content": {
        "months": [
          {"month": "2025-10", "revenue": 70000, "cogs": 18000},
          {"month": "2025-11", "revenue": 75000, "cogs": 19000},
          {"month": "2025-12", "revenue": 80000, "cogs": 20000}
        ]
      }
    },
    {
      "source": "customer_revenue_breakdown",
      "format": "customer_breakdown_json",
      "content": {
        "customers": [
          {"customer_id": "cust_001", "revenue": 11000},
          {"customer_id": "cust_002", "revenue": 9500},
          {"customer_id": "cust_003", "revenue": 8000}
        ]
      }
    },
    {
      "source": "expenses_and_cash",
      "format": "expense_cash_json",
      "content": {"monthly_burn": 85000, "cash_balance": 1200000}
    },
    {
      "source": "cohort_retention",
      "format": "cohort_json",
      "content": {
        "cohorts": [
          {"cohort_month": "2025-09", "starting_customers": 40, "active_after_3mo": 37}
        ]
      }
    },
    {
      "source": "reported_arr",
      "format": "arr_claim_json",
      "content": {"reported_arr": 1500000}
    }
  ]
}
```

---

### Scenario 6: Gross Margin Misrepresentation — SCAE (flag)

Founder claims 80% margin; actual is ~61%.
Expected: `gross_margin_verified: false` (use evaluate with `claimed_values`).

```json
{
  "company_name": "MarginMisrepCo",
  "round_label": "Series A",
  "metrics_records": [
    {
      "source": "monthly_revenue",
      "format": "revenue_timeseries_json",
      "content": {
        "months": [
          {"month": "2025-10", "revenue": 78000, "cogs": 30000},
          {"month": "2025-11", "revenue": 84000, "cogs": 33000},
          {"month": "2025-12", "revenue": 92000, "cogs": 36000}
        ]
      }
    },
    {
      "source": "customer_revenue_breakdown",
      "format": "customer_breakdown_json",
      "content": {
        "customers": [
          {"customer_id": "cust_001", "revenue": 11000},
          {"customer_id": "cust_002", "revenue": 9500},
          {"customer_id": "cust_003", "revenue": 8000},
          {"customer_id": "cust_004", "revenue": 7000},
          {"customer_id": "cust_005", "revenue": 6500}
        ]
      }
    },
    {
      "source": "expenses_and_cash",
      "format": "expense_cash_json",
      "content": {"monthly_burn": 85000, "cash_balance": 1200000}
    },
    {
      "source": "cohort_retention",
      "format": "cohort_json",
      "content": {
        "cohorts": [
          {"cohort_month": "2025-09", "starting_customers": 40, "active_after_3mo": 37}
        ]
      }
    },
    {
      "source": "reported_arr",
      "format": "arr_claim_json",
      "content": {"reported_arr": 1100000}
    }
  ]
}
```

---

### Scenario 7: Mixed Signals (two flags — growth ok, structure risky)

Good growth and margin. Short runway (4.7 mo) + high concentration (38%).
Expected: `customer_concentration_flag: true`, `runway_flag: true`.

```json
{
  "company_name": "MixedSignalsCo",
  "round_label": "Series A",
  "metrics_records": [
    {
      "source": "monthly_revenue",
      "format": "revenue_timeseries_json",
      "content": {
        "months": [
          {"month": "2025-10", "revenue": 78000, "cogs": 19000},
          {"month": "2025-11", "revenue": 90000, "cogs": 22000},
          {"month": "2025-12", "revenue": 104000, "cogs": 25000}
        ]
      }
    },
    {
      "source": "customer_revenue_breakdown",
      "format": "customer_breakdown_json",
      "content": {
        "customers": [
          {"customer_id": "cust_001", "revenue": 39520},
          {"customer_id": "cust_002", "revenue": 20800},
          {"customer_id": "cust_003", "revenue": 18000},
          {"customer_id": "cust_004", "revenue": 14560},
          {"customer_id": "cust_005", "revenue": 11120}
        ]
      }
    },
    {
      "source": "expenses_and_cash",
      "format": "expense_cash_json",
      "content": {"monthly_burn": 95000, "cash_balance": 450000}
    },
    {
      "source": "cohort_retention",
      "format": "cohort_json",
      "content": {
        "cohorts": [
          {"cohort_month": "2025-09", "starting_customers": 40, "active_after_3mo": 37}
        ]
      }
    },
    {
      "source": "reported_arr",
      "format": "arr_claim_json",
      "content": {"reported_arr": 1248000}
    }
  ]
}
```

---

## Step 2 — Evaluate

Replace `{diligence_id}` with the UUID from step 1.

### Without claimed values (inspector only — no tolerance checks)

```json
{}
```

### With claimed values (triggers claim tolerance verification)

```json
{
  "claimed_values": {
    "mom_growth_rate": 0.09,
    "gross_margin_pct": 0.76
  }
}
```

### Margin misrepresentation — claim triggers flag

Pair with Scenario 6. Claimed 80% is >5% off from computed ~61%.

```json
{
  "claimed_values": {
    "mom_growth_rate": 0.09,
    "gross_margin_pct": 0.80
  }
}
```

### Honest overclaim — just within tolerance

Claimed 78% vs computed ~76%. Within the 5% tolerance band.
Expected: `gross_margin_verified: true`.

```json
{
  "claimed_values": {
    "mom_growth_rate": 0.09,
    "gross_margin_pct": 0.78
  }
}
```

---

## Step 3 — Investor Thresholds (4 Profiles)

Replace `{diligence_id}` with the UUID from step 1.

### Profile 1: Lenient Seed Investor

Passes all 7 founder scenarios.

```json
{
  "investor_id": "inv-seed-lenient-001",
  "min_mom_growth": 0.03,
  "max_customer_concentration_pct": 0.50,
  "min_gross_margin": 0.40,
  "min_runway_months": 3.0,
  "max_monthly_churn_pct": 0.15,
  "max_arr_delta_pct": 0.70,
  "disclosure_on_mismatch": "category_only"
}
```

---

### Profile 2: Strict Growth Investor

Requires ≥10% MoM and tight ARR consistency. Only clean high-growth passes.

```json
{
  "investor_id": "inv-growth-strict-002",
  "min_mom_growth": 0.10,
  "max_arr_delta_pct": 0.05,
  "disclosure_on_mismatch": "full_threshold"
}
```

---

### Profile 3: Concentration-Sensitive Investor

Will not tolerate >25% customer concentration. Only clean_series_a passes.

```json
{
  "investor_id": "inv-conc-sensitive-003",
  "max_customer_concentration_pct": 0.25,
  "disclosure_on_mismatch": "category_only"
}
```

---

### Profile 4: Runway-Focused Investor

Minimum 12-month runway. Fails runway_risk and mixed_signals.

```json
{
  "investor_id": "inv-runway-focused-004",
  "min_runway_months": 12.0,
  "disclosure_on_mismatch": "category_only"
}
```

---

### Profile 5: Silent Investor (no mismatch details)

All thresholds standard; founder learns nothing on a miss.

```json
{
  "investor_id": "inv-silent-005",
  "min_mom_growth": 0.05,
  "max_customer_concentration_pct": 0.30,
  "min_gross_margin": 0.60,
  "min_runway_months": 9.0,
  "max_monthly_churn_pct": 0.05,
  "max_arr_delta_pct": 0.10,
  "disclosure_on_mismatch": "none"
}
```

---

### Profile 6: Fully Transparent Investor

Full threshold disclosed on any miss — founder sees exact numbers.

```json
{
  "investor_id": "inv-transparent-006",
  "min_mom_growth": 0.05,
  "max_customer_concentration_pct": 0.30,
  "min_gross_margin": 0.60,
  "min_runway_months": 9.0,
  "max_monthly_churn_pct": 0.05,
  "max_arr_delta_pct": 0.10,
  "disclosure_on_mismatch": "full_threshold"
}
```

---

## Step 4 — Match

No body required. Replace both IDs in the URL.

```
POST /api/fundraising/diligence/{diligence_id}/match/{threshold_id}
```

### Fetch match result as founder

```
GET /api/fundraising/match/{match_id}?viewer=founder
```

### Fetch match result as investor

```
GET /api/fundraising/match/{match_id}?viewer=investor
```

---

## Step 5 — Negotiation

Requires an *evaluated* `diligence_id` (step 2 must have run first).

### Scenario A: Healthy deal — agreement expected

Clean metrics. Reasonable valuation gap. Expected: `agreed: true`.

```json
{
  "diligence_id": "REPLACE_WITH_EVALUATED_DILIGENCE_ID",
  "investor_id": "vc-firm-alpha",
  "investor_max_valuation": 12000000.0,
  "investor_investment_amount": 2000000.0,
  "investor_target_ownership_pct": 15.0,
  "investor_requirements": "Strong SaaS metrics, experienced founding team, clear path to Series B.",
  "founder_floor_valuation": 8000000.0,
  "founder_valuation_ask": 14000000.0,
  "max_rounds": 8
}
```

---

### Scenario B: Tight margin — arbitration likely

Floor and cap are close. High chance of deadlock and arbitration.

```json
{
  "diligence_id": "REPLACE_WITH_EVALUATED_DILIGENCE_ID",
  "investor_id": "vc-firm-beta",
  "investor_max_valuation": 9000000.0,
  "investor_investment_amount": 1500000.0,
  "investor_target_ownership_pct": 18.0,
  "investor_requirements": "Need clean cap table, board seat, pro-rata rights.",
  "founder_floor_valuation": 8500000.0,
  "founder_valuation_ask": 12000000.0,
  "max_rounds": 6
}
```

---

### Scenario C: Aggressive investor — gap too wide

Investor cap is below founder floor. Expected: `agreed: false` or arbitrated settlement.

```json
{
  "diligence_id": "REPLACE_WITH_EVALUATED_DILIGENCE_ID",
  "investor_id": "vc-firm-gamma",
  "investor_max_valuation": 5000000.0,
  "investor_investment_amount": 1000000.0,
  "investor_target_ownership_pct": 25.0,
  "investor_requirements": "Distressed entry price, large ownership required.",
  "founder_floor_valuation": 8000000.0,
  "founder_valuation_ask": 15000000.0,
  "max_rounds": 5
}
```

---

### Scenario D: Quick close — narrow gap

Investor cap above founder ask. Should agree in 1–2 rounds.

```json
{
  "diligence_id": "REPLACE_WITH_EVALUATED_DILIGENCE_ID",
  "investor_id": "vc-firm-delta",
  "investor_max_valuation": 16000000.0,
  "investor_investment_amount": 3000000.0,
  "investor_target_ownership_pct": 15.0,
  "investor_requirements": "Conviction investment, flexible on terms.",
  "founder_floor_valuation": 12000000.0,
  "founder_valuation_ask": 14000000.0,
  "max_rounds": 4
}
```

---

### Scenario E: Max rounds stress test

20-round cap to observe full convergence dynamics.

```json
{
  "diligence_id": "REPLACE_WITH_EVALUATED_DILIGENCE_ID",
  "investor_id": "vc-firm-epsilon",
  "investor_max_valuation": 11000000.0,
  "investor_investment_amount": 2500000.0,
  "investor_target_ownership_pct": 20.0,
  "investor_requirements": "Institutional-grade diligence completed. Board governance required.",
  "founder_floor_valuation": 9000000.0,
  "founder_valuation_ask": 18000000.0,
  "max_rounds": 20
}
```

---

## PowerShell One-Liners

### Ingest — Clean Series A

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/fundraising/diligence/ingest" -ContentType "application/json" -Body '{"company_name":"Acme Software Inc","round_label":"Series A","metrics_records":[{"source":"monthly_revenue","format":"revenue_timeseries_json","content":{"months":[{"month":"2025-10","revenue":78000,"cogs":19000},{"month":"2025-11","revenue":84000,"cogs":20500},{"month":"2025-12","revenue":92000,"cogs":22000}]}},{"source":"customer_revenue_breakdown","format":"customer_breakdown_json","content":{"customers":[{"customer_id":"cust_001","revenue":11000},{"customer_id":"cust_002","revenue":9500},{"customer_id":"cust_003","revenue":8000},{"customer_id":"cust_004","revenue":7000},{"customer_id":"cust_005","revenue":6500},{"customer_id":"cust_006","revenue":5000}]}},{"source":"expenses_and_cash","format":"expense_cash_json","content":{"monthly_burn":85000,"cash_balance":1200000}},{"source":"cohort_retention","format":"cohort_json","content":{"cohorts":[{"cohort_month":"2025-09","starting_customers":40,"active_after_3mo":37}]}},{"source":"reported_arr","format":"arr_claim_json","content":{"reported_arr":1100000}}]}'
```

### Ingest — ARR Inflation (SCAE)

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/fundraising/diligence/ingest" -ContentType "application/json" -Body '{"company_name":"InflatedARRCo","round_label":"Series A","metrics_records":[{"source":"monthly_revenue","format":"revenue_timeseries_json","content":{"months":[{"month":"2025-10","revenue":70000,"cogs":18000},{"month":"2025-11","revenue":75000,"cogs":19000},{"month":"2025-12","revenue":80000,"cogs":20000}]}},{"source":"customer_revenue_breakdown","format":"customer_breakdown_json","content":{"customers":[{"customer_id":"cust_001","revenue":11000},{"customer_id":"cust_002","revenue":9500},{"customer_id":"cust_003","revenue":8000}]}},{"source":"expenses_and_cash","format":"expense_cash_json","content":{"monthly_burn":85000,"cash_balance":1200000}},{"source":"cohort_retention","format":"cohort_json","content":{"cohorts":[{"cohort_month":"2025-09","starting_customers":40,"active_after_3mo":37}]}},{"source":"reported_arr","format":"arr_claim_json","content":{"reported_arr":1500000}}]}'
```

### Evaluate — with claimed values

Replace `{id}`:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/fundraising/diligence/{id}/evaluate" -ContentType "application/json" -Body '{"claimed_values":{"mom_growth_rate":0.09,"gross_margin_pct":0.76}}'
```

### Evaluate — no claims

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/fundraising/diligence/{id}/evaluate" -ContentType "application/json" -Body '{}'
```

### Submit investor thresholds — strict growth

Replace `{did}`:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/fundraising/diligence/{did}/investor-thresholds" -ContentType "application/json" -Body '{"investor_id":"inv-growth-strict-002","min_mom_growth":0.10,"max_arr_delta_pct":0.05,"disclosure_on_mismatch":"full_threshold"}'
```

### Run match

Replace `{did}` and `{tid}`:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/fundraising/diligence/{did}/match/{tid}" -ContentType "application/json" -Body '{}'
```

### Fetch match — founder view

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/fundraising/match/{match_id}?viewer=founder"
```

### Fetch match — investor view

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/fundraising/match/{match_id}?viewer=investor"
```

### Negotiation — healthy deal

Replace `{did}`:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/fundraising/negotiation/run" -ContentType "application/json" -Body '{"diligence_id":"{did}","investor_id":"vc-firm-alpha","investor_max_valuation":12000000.0,"investor_investment_amount":2000000.0,"investor_target_ownership_pct":15.0,"investor_requirements":"Strong SaaS metrics, experienced founding team.","founder_floor_valuation":8000000.0,"founder_valuation_ask":14000000.0,"max_rounds":8}'
```

### Negotiation — tight margin (arbitration likely)

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/fundraising/negotiation/run" -ContentType "application/json" -Body '{"diligence_id":"{did}","investor_id":"vc-firm-beta","investor_max_valuation":9000000.0,"investor_investment_amount":1500000.0,"investor_target_ownership_pct":18.0,"investor_requirements":"Board seat, pro-rata rights required.","founder_floor_valuation":8500000.0,"founder_valuation_ask":12000000.0,"max_rounds":6}'
```

---

## Match Matrix Reference

Expected `overall_match` for each scenario × investor profile combination.

| Founder Scenario | lenient_seed | strict_growth | conc_sensitive | runway_focused |
|-----------------|:------------:|:-------------:|:--------------:|:--------------:|
| Clean Series A | ✅ | ❌ (growth) | ✅ | ✅ |
| Customer concentration | ✅ | ✅ | ❌ (conc) | ✅ |
| Runway risk | ✅ | ❌ (growth) | ❌ (conc)* | ❌ (runway) |
| Churn risk | ✅ | ❌ (growth) | ❌ (conc)* | ✅ |
| ARR inflation | ✅ | ❌ (arr) | ❌ (conc)* | ✅ |
| Margin misrep | ✅ | ❌ (growth) | ❌ (conc)* | ✅ |
| Mixed signals | ✅ | ✅ | ❌ (conc) | ❌ (runway) |

*scenarios 3–6 also fail concentration_sensitive because those fixtures have a single customer at 23%+ of revenue.

---

## Response Shape Reference

### DiligenceEvaluateResponse — inspector_findings

```json
{
  "mom_growth_computed": 0.086,
  "mom_growth_verified": true,
  "top_customer_pct": 0.234,
  "customer_concentration_flag": false,
  "gross_margin_computed": 0.758,
  "gross_margin_verified": true,
  "runway_months_computed": 14.1,
  "runway_flag": false,
  "churn_rate_computed": 0.025,
  "churn_flag": false,
  "arr_delta_pct": -0.004,
  "arr_consistency_verified": true,
  "any_flag_raised": false
}
```

### FundraisingNegotiationCredential — transcript entry

```json
{
  "round": 1,
  "role": "seller",
  "action": "offer",
  "price": 14000000.0,
  "reasoning": "Opening at $14M based on 8.6% MoM growth and 75.8% gross margins..."
}
```

### MatchRunResponse — founder view (category_only disclosure)

```json
{
  "overall_match": false,
  "metric_results": [
    {"metric": "mom_growth_rate", "label": "MoM Growth", "passed": true},
    {"metric": "gross_margin_pct", "label": "Gross Margin", "passed": false}
  ]
}
```

### MatchRunResponse — investor view (always full)

```json
{
  "overall_match": false,
  "metric_results": [
    {
      "metric": "gross_margin_pct",
      "label": "Gross Margin",
      "investor_threshold": 0.60,
      "passed": false
    }
  ]
}
```
