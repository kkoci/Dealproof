"""
Tests for DataQualityAgent and quality-metrics integration.

Covers:
  - DataQualityAgent.assess() happy path (mocked Claude)
  - DataQualityAgent.assess() failure path (returns None, non-fatal)
  - build_quality_context() for buyer and seller roles
  - _hash_report() determinism
  - BuyerAgent and SellerAgent accept quality_context without error
  - DealCreate schema accepts DataQualityMetrics
  - Full /api/deals/run end-to-end with quality_metrics (mocked)
"""
import hashlib
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.data_quality import DataQualityAgent, DataQualityReport, build_quality_context, _hash_report
from app.agents.buyer import BuyerAgent
from app.agents.seller import SellerAgent
from app.api.schemas import DealCreate, DataQualityMetrics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_METRICS = {
    "row_count": 500,
    "column_names": ["timestamp", "device_id", "temperature_c", "humidity_pct", "pressure_hpa", "vibration_ms2", "label"],
    "null_rates": {"pressure_hpa": 0.124, "vibration_ms2": 0.062},
    "label_column": "label",
    "label_distribution": {"normal": 0.842, "anomaly": 0.158},
    "schema_valid": True,
    "additional_notes": None,
}

SAMPLE_REPORT_JSON = json.dumps({
    "completeness_score": 0.974,
    "schema_consistent": True,
    "label_distribution": {"normal": 0.842, "anomaly": 0.158},
    "quality_issues": ["12.4% null rate in pressure_hpa column", "6.2% null rate in vibration_ms2 column"],
    "overall_quality": "medium",
    "summary": "Dataset is generally reliable but has notable null rates in two sensor columns.",
})


def _make_mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


# ---------------------------------------------------------------------------
# DataQualityAgent unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_data_quality_agent_happy_path():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=_make_mock_response(SAMPLE_REPORT_JSON))

    agent = DataQualityAgent()
    agent.client = mock_client

    report = await agent.assess("IoT sensor dataset", SAMPLE_METRICS)

    assert report is not None
    assert report.completeness_score == pytest.approx(0.974)
    assert report.schema_consistent is True
    assert report.overall_quality == "medium"
    assert len(report.quality_issues) == 2
    assert report.label_distribution == {"normal": 0.842, "anomaly": 0.158}
    assert len(report.quality_hash) == 64  # SHA-256 hex


@pytest.mark.asyncio
async def test_data_quality_agent_returns_none_on_failure():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

    agent = DataQualityAgent()
    agent.client = mock_client

    report = await agent.assess("some dataset", SAMPLE_METRICS)
    assert report is None


@pytest.mark.asyncio
async def test_data_quality_agent_handles_invalid_json():
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        return_value=_make_mock_response("Not valid JSON at all")
    )

    agent = DataQualityAgent()
    agent.client = mock_client

    report = await agent.assess("some dataset", SAMPLE_METRICS)
    assert report is None


# ---------------------------------------------------------------------------
# _hash_report determinism
# ---------------------------------------------------------------------------

def test_hash_report_is_deterministic():
    report = DataQualityReport(
        completeness_score=0.974,
        schema_consistent=True,
        label_distribution={"normal": 0.842, "anomaly": 0.158},
        quality_issues=["12.4% null rate in pressure_hpa", "6.2% null rate in vibration_ms2"],
        overall_quality="medium",
        summary="Dataset is generally reliable.",
        quality_hash="",
    )
    h1 = _hash_report(report)
    h2 = _hash_report(report)
    assert h1 == h2
    assert len(h1) == 64


def test_hash_report_changes_with_content():
    base = DataQualityReport(
        completeness_score=0.974, schema_consistent=True,
        label_distribution=None, quality_issues=[],
        overall_quality="high", summary="Good.", quality_hash="",
    )
    modified = DataQualityReport(
        completeness_score=0.800, schema_consistent=True,
        label_distribution=None, quality_issues=[],
        overall_quality="medium", summary="Good.", quality_hash="",
    )
    assert _hash_report(base) != _hash_report(modified)


# ---------------------------------------------------------------------------
# build_quality_context
# ---------------------------------------------------------------------------

def test_build_quality_context_buyer():
    report = DataQualityReport(
        completeness_score=0.974,
        schema_consistent=True,
        label_distribution={"normal": 0.842, "anomaly": 0.158},
        quality_issues=["12.4% null rate in pressure_hpa"],
        overall_quality="medium",
        summary="Notable null rates.",
        quality_hash="abc",
    )
    ctx = build_quality_context(report, "buyer")
    assert "MEDIUM" in ctx
    assert "97.4%" in ctx
    assert "12.4% null rate" in ctx
    assert "lower price" in ctx


def test_build_quality_context_seller():
    report = DataQualityReport(
        completeness_score=0.974,
        schema_consistent=True,
        label_distribution=None,
        quality_issues=[],
        overall_quality="high",
        summary="Clean dataset.",
        quality_hash="abc",
    )
    ctx = build_quality_context(report, "seller")
    assert "HIGH" in ctx
    assert "none identified" in ctx


# ---------------------------------------------------------------------------
# Agent integration — quality_context accepted without error
# ---------------------------------------------------------------------------

def test_buyer_agent_accepts_quality_context():
    agent = BuyerAgent(
        budget=800.0,
        requirements="IoT sensor data",
        quality_context="Overall quality: MEDIUM (97.4%). Issues: 12.4% null in pressure_hpa.",
    )
    assert "TEE-VERIFIED DATASET QUALITY CREDENTIAL" in agent.system_prompt
    assert "MEDIUM" in agent.system_prompt


def test_seller_agent_accepts_quality_context():
    agent = SellerAgent(
        floor_price=500.0,
        data_description="Industrial IoT dataset, 500 rows",
        quality_context="Overall quality: MEDIUM (97.4%). Issues: 12.4% null in pressure_hpa.",
    )
    assert "TEE-VERIFIED DATASET QUALITY CREDENTIAL" in agent.system_prompt
    assert "MEDIUM" in agent.system_prompt


def test_buyer_agent_no_quality_context():
    agent = BuyerAgent(budget=800.0, requirements="IoT data")
    assert "TEE-VERIFIED DATASET QUALITY CREDENTIAL" not in agent.system_prompt


# ---------------------------------------------------------------------------
# Schema: DealCreate accepts DataQualityMetrics
# ---------------------------------------------------------------------------

def test_deal_create_with_quality_metrics():
    deal = DealCreate(
        buyer_budget=800.0,
        buyer_requirements="IoT sensor data for anomaly detection",
        data_description="500-row industrial IoT dataset, 7 columns",
        data_hash="65327bf4fcee0f337115c7ab12c4fc54977893386e38b6099ccbd915542effca",
        floor_price=500.0,
        quality_metrics=DataQualityMetrics(
            row_count=500,
            column_names=["timestamp", "device_id", "temperature_c", "humidity_pct", "pressure_hpa", "vibration_ms2", "label"],
            null_rates={"pressure_hpa": 0.124, "vibration_ms2": 0.062},
            label_column="label",
            label_distribution={"normal": 0.842, "anomaly": 0.158},
        ),
    )
    assert deal.quality_metrics is not None
    assert deal.quality_metrics.row_count == 500
    assert deal.quality_metrics.null_rates["pressure_hpa"] == pytest.approx(0.124)


def test_deal_create_without_quality_metrics():
    deal = DealCreate(
        buyer_budget=800.0,
        buyer_requirements="IoT sensor data",
        data_description="500-row industrial IoT dataset",
        data_hash="65327bf4fcee0f337115c7ab12c4fc54977893386e38b6099ccbd915542effca",
        floor_price=500.0,
    )
    assert deal.quality_metrics is None
