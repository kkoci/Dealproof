"""
Fundraising diligence tests — Phase 4.

20 tests covering:
  - Corpus root determinism (2)
  - MetricsInspectorAgent hard findings (12 — six metrics × pass/flag)
  - SCAE scenarios: arr_inflation + margin_misrepresentation (2)
  - Full HTTP pipeline: ingest + evaluate endpoints (2)
  - Mixed signals scenario (1)
  - Credential hash present in response (1)

External I/O mocked:
  - MetricsEvaluatorAgent.evaluate → AsyncMock (avoids LLM call)
  - sign_result → AsyncMock (avoids tappd socket)
  - app.db.DB_PATH → tmp file (same pattern as test_e2e.py)
"""
import hashlib
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.fundraising.metrics_hasher import (
    compute_metrics_corpus_root,
    extract_metric_evidence,
)
from app.fundraising.agents.metrics_inspector import (
    MetricsInspectorAgent,
    CONCENTRATION_FLAG_PCT,
    RUNWAY_FLAG_MONTHS,
    CHURN_FLAG_MONTHLY,
    CLAIM_TOLERANCE,
    ARR_TOLERANCE,
)
from scripts.generate_fundraising_fixtures import SCENARIOS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _records(scenario_name: str) -> list[dict]:
    return [r for r in SCENARIOS[scenario_name]["metrics_records"]]


def _evidence(scenario_name: str) -> dict:
    return extract_metric_evidence(_records(scenario_name))


def _inspect(scenario_name: str, claimed_values: dict | None = None):
    evidence = _evidence(scenario_name)
    cv = claimed_values or SCENARIOS[scenario_name].get("claimed_values")
    return MetricsInspectorAgent().inspect(evidence, cv)


# ---------------------------------------------------------------------------
# Corpus root determinism (2)
# ---------------------------------------------------------------------------

def test_corpus_root_determinism():
    records = _records("clean_series_a")
    root1 = compute_metrics_corpus_root(records)
    root2 = compute_metrics_corpus_root(records)
    assert root1 == root2
    assert len(root1) == 64  # SHA-256 hex


def test_corpus_root_changes_with_content():
    root_a = compute_metrics_corpus_root(_records("clean_series_a"))
    root_b = compute_metrics_corpus_root(_records("arr_inflation"))
    assert root_a != root_b


# ---------------------------------------------------------------------------
# MetricsInspectorAgent — MoM growth (2)
# ---------------------------------------------------------------------------

def test_inspector_mom_growth_verified():
    report = _inspect("clean_series_a")
    # expected claimed ≈ 0.09, computed ≈ 0.090 — within CLAIM_TOLERANCE
    assert report.mom_growth_verified is True
    assert report.mom_growth_computed is not None
    assert report.mom_growth_computed > 0


def test_inspector_mom_growth_mismatch():
    # Inject a claimed value far from actual computed rate
    evidence = _evidence("clean_series_a")
    report = MetricsInspectorAgent().inspect(evidence, {"mom_growth_rate": 0.50})
    assert report.mom_growth_verified is False


# ---------------------------------------------------------------------------
# MetricsInspectorAgent — Customer concentration (2)
# ---------------------------------------------------------------------------

def test_inspector_customer_concentration_ok():
    report = _inspect("clean_series_a")
    assert report.customer_concentration_flag is False
    assert report.top_customer_pct is not None
    assert report.top_customer_pct < CONCENTRATION_FLAG_PCT


def test_inspector_customer_concentration_flagged():
    report = _inspect("customer_concentration_risk")
    assert report.customer_concentration_flag is True
    assert report.top_customer_pct >= CONCENTRATION_FLAG_PCT


# ---------------------------------------------------------------------------
# MetricsInspectorAgent — Gross margin (2)
# ---------------------------------------------------------------------------

def test_inspector_gross_margin_verified():
    report = _inspect("clean_series_a")
    assert report.gross_margin_verified is True
    assert report.gross_margin_computed is not None
    # Computed ≈ 76%, claimed 0.76 — well within 5%
    assert abs(report.gross_margin_computed - 0.76) <= CLAIM_TOLERANCE


def test_inspector_gross_margin_mismatch():
    # margin_misrepresentation: actual ≈ 61%, claimed 80%
    report = _inspect("margin_misrepresentation")
    assert report.gross_margin_verified is False
    assert report.gross_margin_computed is not None
    assert report.gross_margin_computed < 0.65  # computed is ~61%


# ---------------------------------------------------------------------------
# MetricsInspectorAgent — Runway (2)
# ---------------------------------------------------------------------------

def test_inspector_runway_ok():
    report = _inspect("clean_series_a")
    assert report.runway_flag is False
    assert report.runway_months_computed is not None
    assert report.runway_months_computed >= RUNWAY_FLAG_MONTHS


def test_inspector_runway_flagged():
    report = _inspect("runway_risk")
    assert report.runway_flag is True
    assert report.runway_months_computed is not None
    assert report.runway_months_computed < RUNWAY_FLAG_MONTHS


# ---------------------------------------------------------------------------
# MetricsInspectorAgent — Churn rate (2)
# ---------------------------------------------------------------------------

def test_inspector_churn_ok():
    report = _inspect("clean_series_a")
    assert report.churn_flag is False
    assert report.churn_rate_computed is not None
    assert report.churn_rate_computed <= CHURN_FLAG_MONTHLY


def test_inspector_churn_flagged():
    report = _inspect("churn_risk")
    assert report.churn_flag is True
    assert report.churn_rate_computed is not None
    assert report.churn_rate_computed > CHURN_FLAG_MONTHLY


# ---------------------------------------------------------------------------
# MetricsInspectorAgent — ARR consistency (2)
# ---------------------------------------------------------------------------

def test_inspector_arr_consistency_verified():
    report = _inspect("clean_series_a")
    assert report.arr_consistency_verified is True
    assert report.arr_delta_pct is not None
    assert abs(report.arr_delta_pct) <= ARR_TOLERANCE


def test_inspector_arr_consistency_flagged():
    report = _inspect("arr_inflation")
    assert report.arr_consistency_verified is False
    assert report.arr_delta_pct is not None
    assert abs(report.arr_delta_pct) > ARR_TOLERANCE


# ---------------------------------------------------------------------------
# SCAE tests (2)
# ---------------------------------------------------------------------------

def test_scae_arr_inflation():
    """
    SCAE: founder reports ARR of $1.5M.
    MetricsInspectorAgent recomputes from actual subscription records:
    last_month_revenue × 12 = $960k → delta ≈ +56%.
    Inspector must flag this regardless of the reported figure.
    """
    report = _inspect("arr_inflation")
    assert report.arr_consistency_verified is False, (
        "Inspector should flag ARR inflation (reported $1.5M, computed $960k)"
    )
    assert report.any_flag_raised is True
    # Sanity: delta is meaningfully positive (founder inflated)
    assert report.arr_delta_pct is not None
    assert report.arr_delta_pct > 0.40  # ≥40% inflation


def test_scae_margin_misrepresentation():
    """
    SCAE: founder claims 80% gross margin.
    MetricsInspectorAgent computes from COGS records: (rev - cogs) / rev ≈ 61%.
    |0.61 - 0.80| = 0.19 > CLAIM_TOLERANCE (5%) → verified=False.
    """
    report = _inspect("margin_misrepresentation")
    assert report.gross_margin_verified is False, (
        "Inspector should flag margin misrepresentation (claimed 80%, computed ~61%)"
    )
    assert report.any_flag_raised is True
    assert report.gross_margin_computed is not None
    # Computed margin is materially below claim
    assert report.gross_margin_computed < 0.65


# ---------------------------------------------------------------------------
# Mixed signals (1)
# ---------------------------------------------------------------------------

def test_mixed_signals_scenario():
    """
    Good growth + margin; short runway + high customer concentration.
    any_flag_raised=True, but not all metrics are flagged.
    """
    report = _inspect("mixed_signals")
    assert report.any_flag_raised is True
    assert report.customer_concentration_flag is True
    assert report.runway_flag is True
    # Good metrics should still pass
    assert report.churn_flag is False
    assert report.mom_growth_verified is True


# ---------------------------------------------------------------------------
# HTTP pipeline tests (3)
# ---------------------------------------------------------------------------

def _make_client(tmp_db: Path):
    """Return a TestClient with DB patched to a tmp file."""
    import app.db as db_mod
    with patch.object(db_mod, "DB_PATH", tmp_db):
        from app.main import app
        return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def tmp_db(tmp_path):
    return tmp_path / "test_fundraising.db"


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


def test_ingest_endpoint(client):
    resp = client.post("/api/fundraising/diligence/ingest", json=_INGEST_BODY)
    assert resp.status_code == 200
    data = resp.json()
    assert "diligence_id" in data
    assert len(data["corpus_root"]) == 64
    assert len(data["record_hashes"]) == len(_INGEST_BODY["metrics_records"])
    assert "metric_evidence_preview" in data


def test_evaluate_endpoint(client):
    # Ingest first
    ingest = client.post("/api/fundraising/diligence/ingest", json=_INGEST_BODY)
    assert ingest.status_code == 200
    diligence_id = ingest.json()["diligence_id"]

    # Mock LLM evaluator and TDX sign_result
    mock_eval = AsyncMock(return_value=None)  # evaluator returns None → evaluation=null
    mock_sign = AsyncMock(return_value="sim_quote:test_hash_f3")

    with patch("app.fundraising.routes.MetricsEvaluatorAgent.evaluate", mock_eval), \
         patch("app.fundraising.routes.sign_result", mock_sign):
        resp = client.post(
            f"/api/fundraising/diligence/{diligence_id}/evaluate",
            json={"claimed_values": {"mom_growth_rate": 0.09, "gross_margin_pct": 0.76}},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["diligence_id"] == diligence_id
    assert len(data["credential_hash"]) == 64
    assert data["tee_quote"] == "sim_quote:test_hash_f3"
    assert "inspector_findings" in data
    assert data["any_flag_raised"] is False  # clean_series_a — no flags


def test_credential_hash_in_tee_payload(client):
    """
    credential_hash and corpus_root must both appear in the sign_result call's
    terms dict — verifies they are embedded in TDX report_data.
    """
    ingest = client.post("/api/fundraising/diligence/ingest", json=_INGEST_BODY)
    diligence_id = ingest.json()["diligence_id"]

    captured_terms = {}

    async def capture_sign(terms, memory_hash=""):
        captured_terms.update(terms)
        return "sim_quote:captured"

    mock_eval = AsyncMock(return_value=None)

    with patch("app.fundraising.routes.MetricsEvaluatorAgent.evaluate", mock_eval), \
         patch("app.fundraising.routes.sign_result", capture_sign):
        resp = client.post(
            f"/api/fundraising/diligence/{diligence_id}/evaluate",
            json={},
        )

    assert resp.status_code == 200
    assert "credential_hash" in captured_terms
    assert "corpus_root" in captured_terms
    assert "any_flag_raised" in captured_terms
    # credential_hash in response must match what was sent to sign_result
    assert captured_terms["credential_hash"] == resp.json()["credential_hash"]
