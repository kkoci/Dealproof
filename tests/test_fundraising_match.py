"""
Fundraising Negotiation Extension tests.

This file grows phase by phase:
  Ext-Phase 1: InvestorThresholds schema + storage endpoint (tests 1–8)
  Ext-Phase 2: ThresholdMatchAgent deterministic matching (tests 9–22)
  Ext-Phase 3: FundraisingMatchCredential + attestation (tests 23+)
"""
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.fundraising.schemas import InvestorThresholds
from app.fundraising.agents.threshold_match import (
    ThresholdMatchAgent,
    ThresholdMatchResult,
    founder_view,
    investor_view,
)
from scripts.generate_fundraising_fixtures import SCENARIOS


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    return tmp_path / "test_match.db"


@pytest.fixture()
def client(tmp_db):
    import app.db as db_mod
    with patch.object(db_mod, "DB_PATH", tmp_db):
        from app.main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


_INGEST_BODY = {
    "company_name": "Acme Software Inc",
    "round_label": "Series A",
    "metrics_records": SCENARIOS["clean_series_a"]["metrics_records"],
}


def _ingest(client) -> str:
    """Ingest a diligence record and return its diligence_id."""
    resp = client.post("/api/fundraising/diligence/ingest", json=_INGEST_BODY)
    assert resp.status_code == 200
    return resp.json()["diligence_id"]


# ---------------------------------------------------------------------------
# Ext-Phase 1: InvestorThresholds schema (3 unit tests)
# ---------------------------------------------------------------------------

def test_investor_thresholds_schema_defaults():
    """All threshold fields default to None; disclosure defaults to category_only."""
    t = InvestorThresholds(investor_id="inv-001")
    assert t.min_mom_growth is None
    assert t.max_customer_concentration_pct is None
    assert t.min_gross_margin is None
    assert t.min_runway_months is None
    assert t.max_monthly_churn_pct is None
    assert t.max_arr_delta_pct is None
    assert t.disclosure_on_mismatch == "category_only"


def test_investor_thresholds_full_population():
    """All fields set — schema accepts them without error."""
    t = InvestorThresholds(
        investor_id="inv-vc-42",
        min_mom_growth=0.10,
        max_customer_concentration_pct=0.25,
        min_gross_margin=0.60,
        min_runway_months=12.0,
        max_monthly_churn_pct=0.03,
        max_arr_delta_pct=0.10,
        disclosure_on_mismatch="full_threshold",
    )
    assert t.investor_id == "inv-vc-42"
    assert t.min_mom_growth == pytest.approx(0.10)
    assert t.disclosure_on_mismatch == "full_threshold"


def test_investor_thresholds_disclosure_none_variant():
    t = InvestorThresholds(investor_id="inv-stealth", disclosure_on_mismatch="none")
    assert t.disclosure_on_mismatch == "none"


# ---------------------------------------------------------------------------
# Ext-Phase 1: POST endpoint (5 HTTP tests)
# ---------------------------------------------------------------------------

def test_submit_thresholds_returns_201(client):
    diligence_id = _ingest(client)
    resp = client.post(
        f"/api/fundraising/diligence/{diligence_id}/investor-thresholds",
        json={
            "investor_id": "inv-seed-001",
            "min_mom_growth": 0.05,
            "min_runway_months": 9.0,
            "disclosure_on_mismatch": "category_only",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "threshold_id" in data
    assert len(data["threshold_id"]) == 36  # UUID
    assert data["diligence_id"] == diligence_id
    assert data["investor_id"] == "inv-seed-001"
    assert data["disclosure_on_mismatch"] == "category_only"


def test_submit_thresholds_404_on_unknown_diligence(client):
    resp = client.post(
        "/api/fundraising/diligence/nonexistent-id/investor-thresholds",
        json={"investor_id": "inv-x"},
    )
    assert resp.status_code == 404


def test_submit_thresholds_invalid_disclosure_rejected(client):
    diligence_id = _ingest(client)
    resp = client.post(
        f"/api/fundraising/diligence/{diligence_id}/investor-thresholds",
        json={"investor_id": "inv-bad", "disclosure_on_mismatch": "everything"},
    )
    assert resp.status_code == 422


def test_multiple_investors_same_diligence(client):
    """Multiple investors can submit thresholds for the same diligence."""
    diligence_id = _ingest(client)
    for i in range(3):
        resp = client.post(
            f"/api/fundraising/diligence/{diligence_id}/investor-thresholds",
            json={"investor_id": f"inv-{i:03d}"},
        )
        assert resp.status_code == 201

    # Each gets a distinct threshold_id
    ids = set()
    for i in range(3):
        resp = client.post(
            f"/api/fundraising/diligence/{diligence_id}/investor-thresholds",
            json={"investor_id": f"inv-extra-{i}"},
        )
        ids.add(resp.json()["threshold_id"])
    assert len(ids) == 3


# ---------------------------------------------------------------------------
# Ext-Phase 2: ThresholdMatchAgent — helpers
# ---------------------------------------------------------------------------

def _make_thresholds(**kwargs) -> InvestorThresholds:
    return InvestorThresholds(investor_id="inv-test", **kwargs)


# Synthetic inspection_report matching clean_series_a approximate computed values:
# MoM growth ~9%, top customer ~23.4%, gross margin ~76.2%,
# runway ~14.1 months, churn ~2.5%, ARR delta ~-0.36%
_CLEAN_REPORT: dict = {
    "mom_growth_computed":      0.090,
    "mom_growth_verified":      True,
    "top_customer_pct":         0.234,
    "customer_concentration_flag": False,
    "gross_margin_computed":    0.762,
    "gross_margin_verified":    True,
    "runway_months_computed":   14.1,
    "runway_flag":              False,
    "churn_rate_computed":      0.025,
    "churn_flag":               False,
    "arr_delta_pct":            -0.0036,
    "arr_consistency_verified": True,
    "any_flag_raised":          False,
}

# A weaker company: low growth, high concentration, short runway, high churn
_WEAK_REPORT: dict = {
    "mom_growth_computed":      0.030,
    "mom_growth_verified":      True,
    "top_customer_pct":         0.450,
    "customer_concentration_flag": True,
    "gross_margin_computed":    0.420,
    "gross_margin_verified":    True,
    "runway_months_computed":   4.0,
    "runway_flag":              True,
    "churn_rate_computed":      0.090,
    "churn_flag":               True,
    "arr_delta_pct":            0.20,
    "arr_consistency_verified": False,
    "any_flag_raised":          True,
}


# ---------------------------------------------------------------------------
# Ext-Phase 2: full-pass scenario
# ---------------------------------------------------------------------------

def test_match_full_pass_lenient_thresholds():
    """Lenient investor — all specified thresholds met by clean company."""
    thresholds = _make_thresholds(
        min_mom_growth=0.05,                  # clean has 9%  ✓
        max_customer_concentration_pct=0.30,   # clean has 23% ✓
        min_gross_margin=0.60,                 # clean has 76% ✓
        min_runway_months=9.0,                 # clean has 14m ✓
        max_monthly_churn_pct=0.05,            # clean has 2.5% ✓
        max_arr_delta_pct=0.10,                # clean has 0.36% ✓
        disclosure_on_mismatch="category_only",
    )
    agent = ThresholdMatchAgent()
    result = agent.match(_CLEAN_REPORT, thresholds)

    assert result.overall_match is True
    assert all(m.passed for m in result.metric_results)


def test_match_full_pass_subset_of_thresholds():
    """Investor only specifies some thresholds — unset ones don't block the match."""
    thresholds = _make_thresholds(
        min_mom_growth=0.05,
        min_runway_months=9.0,
        # all others None — investor doesn't care
    )
    result = ThresholdMatchAgent().match(_CLEAN_REPORT, thresholds)
    assert result.overall_match is True


# ---------------------------------------------------------------------------
# Ext-Phase 2: full-fail scenario
# ---------------------------------------------------------------------------

def test_match_full_fail_strict_thresholds():
    """Strict investor — weak company fails all specified thresholds."""
    thresholds = _make_thresholds(
        min_mom_growth=0.10,                   # weak has 3%  ✗
        max_customer_concentration_pct=0.20,   # weak has 45% ✗
        min_gross_margin=0.65,                 # weak has 42% ✗
        min_runway_months=12.0,                # weak has 4m  ✗
        max_monthly_churn_pct=0.03,            # weak has 9%  ✗
        max_arr_delta_pct=0.10,                # weak has 20% ✗
    )
    result = ThresholdMatchAgent().match(_WEAK_REPORT, thresholds)

    assert result.overall_match is False
    specified = [m for m in result.metric_results if m.investor_threshold is not None]
    assert all(not m.passed for m in specified)


# ---------------------------------------------------------------------------
# Ext-Phase 2: partial-match scenarios (2)
# ---------------------------------------------------------------------------

def test_match_partial_growth_fails():
    """Investor requires strong MoM growth; clean company misses only that bar."""
    thresholds = _make_thresholds(
        min_mom_growth=0.15,                  # clean has 9%  ✗  ← fails this one
        max_customer_concentration_pct=0.30,   # clean has 23% ✓
        min_gross_margin=0.60,                 # clean has 76% ✓
    )
    result = ThresholdMatchAgent().match(_CLEAN_REPORT, thresholds)

    assert result.overall_match is False

    by_metric = {m.metric: m for m in result.metric_results}
    assert by_metric["mom_growth"].passed is False
    assert by_metric["customer_concentration"].passed is True
    assert by_metric["gross_margin"].passed is True


def test_match_partial_concentration_fails():
    """Concentration-sensitive investor; only that threshold is breached."""
    thresholds = _make_thresholds(
        max_customer_concentration_pct=0.15,   # clean has 23% ✗  ← fails
        min_runway_months=9.0,                 # clean has 14m ✓
        max_monthly_churn_pct=0.05,            # clean has 2.5% ✓
    )
    result = ThresholdMatchAgent().match(_CLEAN_REPORT, thresholds)

    assert result.overall_match is False
    by_metric = {m.metric: m for m in result.metric_results}
    assert by_metric["customer_concentration"].passed is False
    assert by_metric["runway"].passed is True
    assert by_metric["monthly_churn"].passed is True


# ---------------------------------------------------------------------------
# Ext-Phase 2: no thresholds set → always passes
# ---------------------------------------------------------------------------

def test_match_no_thresholds_always_passes():
    """When investor specifies no thresholds, every company matches."""
    thresholds = _make_thresholds()  # all None
    result = ThresholdMatchAgent().match(_WEAK_REPORT, thresholds)
    assert result.overall_match is True
    assert all(m.passed for m in result.metric_results)


# ---------------------------------------------------------------------------
# Ext-Phase 2: disclosure_on_mismatch = "none"
# ---------------------------------------------------------------------------

def test_founder_view_none_shows_only_overall_match():
    thresholds = _make_thresholds(
        min_mom_growth=0.15,   # clean fails this
        disclosure_on_mismatch="none",
    )
    result = ThresholdMatchAgent().match(_CLEAN_REPORT, thresholds)
    view = founder_view(result)

    assert view["overall_match"] is False
    assert "failed_metrics" not in view
    assert "metric_results" not in view
    assert "investor_threshold" not in str(view)
    # Ensure only allowed keys
    assert set(view.keys()) == {"overall_match", "disclosure_level"}


# ---------------------------------------------------------------------------
# Ext-Phase 2: disclosure_on_mismatch = "category_only"
# ---------------------------------------------------------------------------

def test_founder_view_category_only_shows_names_not_values():
    thresholds = _make_thresholds(
        min_mom_growth=0.15,                  # clean fails (9% < 15%)
        max_customer_concentration_pct=0.30,   # clean passes
        disclosure_on_mismatch="category_only",
    )
    result = ThresholdMatchAgent().match(_CLEAN_REPORT, thresholds)
    view = founder_view(result)

    assert view["overall_match"] is False
    assert "failed_metrics" in view
    assert len(view["failed_metrics"]) == 1
    assert "MoM Revenue Growth" in view["failed_metrics"]
    # No threshold values in founder view
    assert "0.15" not in str(view)
    assert "investor_threshold" not in str(view)


def test_founder_view_category_only_no_failures():
    thresholds = _make_thresholds(
        min_mom_growth=0.05,   # clean passes
        disclosure_on_mismatch="category_only",
    )
    result = ThresholdMatchAgent().match(_CLEAN_REPORT, thresholds)
    view = founder_view(result)

    assert view["overall_match"] is True
    assert view["failed_metrics"] == []


# ---------------------------------------------------------------------------
# Ext-Phase 2: disclosure_on_mismatch = "full_threshold"
# ---------------------------------------------------------------------------

def test_founder_view_full_threshold_reveals_investor_bar():
    thresholds = _make_thresholds(
        min_mom_growth=0.15,   # clean fails
        disclosure_on_mismatch="full_threshold",
    )
    result = ThresholdMatchAgent().match(_CLEAN_REPORT, thresholds)
    view = founder_view(result)

    assert view["overall_match"] is False
    assert "metric_results" in view
    growth_entry = next(m for m in view["metric_results"] if m["metric"] == "mom_growth")
    # Investor bar is revealed
    assert growth_entry["investor_threshold"] == pytest.approx(0.15)
    assert growth_entry["passed"] is False
    # But founder's own raw value is NOT in the founder view dict
    assert "founder_value" not in growth_entry


# ---------------------------------------------------------------------------
# Ext-Phase 2: investor view never contains founder raw values
# ---------------------------------------------------------------------------

def test_investor_view_never_contains_founder_raw_values():
    """Investor sees pass/fail + their own thresholds — never founder's raw numbers."""
    thresholds = _make_thresholds(
        min_mom_growth=0.05,
        max_customer_concentration_pct=0.30,
        disclosure_on_mismatch="full_threshold",
    )
    result = ThresholdMatchAgent().match(_CLEAN_REPORT, thresholds)
    inv_view = investor_view(result)

    for entry in inv_view["metric_results"]:
        assert "founder_value" not in entry

    # Raw computed values must not appear in the investor view
    view_str = str(inv_view)
    assert "0.090" not in view_str  # mom_growth_computed
    assert "0.762" not in view_str  # gross_margin_computed
    assert "14.1" not in view_str   # runway


def test_investor_view_always_full_regardless_of_disclosure():
    """disclosure_on_mismatch 'none' on founder side doesn't restrict investor view."""
    thresholds = _make_thresholds(
        min_mom_growth=0.15,   # fail
        disclosure_on_mismatch="none",
    )
    result = ThresholdMatchAgent().match(_CLEAN_REPORT, thresholds)
    inv_view = investor_view(result)

    # Investor still gets per-metric results even if disclosure='none' for founder
    assert "metric_results" in inv_view
    growth = next(m for m in inv_view["metric_results"] if m["metric"] == "mom_growth")
    assert growth["passed"] is False


# ---------------------------------------------------------------------------
# Ext-Phase 2: missing metric data treated as fail
# ---------------------------------------------------------------------------

def test_match_missing_metric_data_fails():
    """If a metric isn't in inspection_report but investor requires it, it fails."""
    sparse_report = {k: None for k in _CLEAN_REPORT}  # all None
    thresholds = _make_thresholds(min_runway_months=9.0)
    result = ThresholdMatchAgent().match(sparse_report, thresholds)

    assert result.overall_match is False
    by_metric = {m.metric: m for m in result.metric_results}
    assert by_metric["runway"].passed is False


# ---------------------------------------------------------------------------
# placeholder: investor info never in test_investor_thresholds_not_exposed_by_founder_endpoint
# (defined below — keep original position)
# ---------------------------------------------------------------------------

def test_investor_thresholds_not_exposed_by_founder_endpoint(client):
    """
    GET /api/fundraising/diligence/{id} must not return investor threshold data.
    The founder endpoint shows only the founder's own credential.
    """
    diligence_id = _ingest(client)

    # Submit investor thresholds
    client.post(
        f"/api/fundraising/diligence/{diligence_id}/investor-thresholds",
        json={
            "investor_id": "inv-private",
            "min_mom_growth": 0.15,
            "max_customer_concentration_pct": 0.20,
            "disclosure_on_mismatch": "none",
        },
    )

    # Fetch via founder-facing GET — must not contain investor data
    resp = client.get(f"/api/fundraising/diligence/{diligence_id}")
    assert resp.status_code == 200
    body = resp.json()

    # Raw threshold values must not appear anywhere in the founder response
    body_str = str(body)
    assert "inv-private" not in body_str
    assert "min_mom_growth" not in body_str
    assert "0.15" not in body_str
    assert "0.20" not in body_str
    assert "investor_thresholds" not in body_str
