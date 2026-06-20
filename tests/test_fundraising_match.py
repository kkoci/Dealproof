"""
Fundraising Negotiation Extension tests.

This file grows phase by phase:
  Ext-Phase 1: InvestorThresholds schema + storage endpoint (tests 1–8)
  Ext-Phase 2: ThresholdMatchAgent deterministic matching (tests 9–18)
  Ext-Phase 3: FundraisingMatchCredential + attestation (tests 19–25)
"""
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.fundraising.schemas import InvestorThresholds
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
