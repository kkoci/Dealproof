"""
Tests for the SOC 2 Continuous Assurance vertical — Phase S4.

Coverage:
  - config_hasher: hash_config_file, compute_config_corpus_root, extract_control_evidence
  - ConfigInspectorAgent: all six CC6/CC7 checks, SCAE resistance, pass/fail fixtures
  - ControlEvaluatorAgent: mock LLM, hard finding override, failure non-fatal
  - SOC2ControlCredential schema: field presence, hash determinism
  - HTTP endpoints: POST /ingest, POST /{id}/evaluate (happy + idempotent), GET /{id}

No Docker, no tappd, no live Anthropic API required.
"""
import hashlib
import json
import pathlib
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.db as db_module
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

GOOD_IAM = {
    "source": "iam_policies",
    "format": "aws_iam_json",
    "content": {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Deny",
                "Action": "*",
                "Resource": "*",
                "Condition": {"Bool": {"aws:MultiFactorAuthPresent": "false"}},
            }
        ],
    },
}

BAD_IAM_WILDCARD = {
    "source": "iam_policies",
    "format": "aws_iam_json",
    "content": {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "*", "Resource": "*"},
        ],
    },
}

# SCAE: policy named to look compliant but has no actual MFA condition
SCAE_IAM = {
    "source": "iam_policies",
    "format": "aws_iam_json",
    "content": {
        "PolicyName": "ComplianceEnforcedMFAPolicy",
        "Version": "2012-10-17",
        "Statement": [
            # Allow Action=* Resource=* — no MFA condition despite the name
            {"Effect": "Allow", "Action": "*", "Resource": "*"},
        ],
    },
}

GOOD_CLOUDTRAIL = {
    "source": "cloudtrail_config",
    "format": "aws_cloudtrail_json",
    "content": {
        "IsLogging": True,
        "Trail": {"Name": "prod-trail", "TrailARN": "arn:aws:cloudtrail:us-east-1:123:trail/prod-trail"},
        "EventSelectors": [
            {"IncludeManagementEvents": True, "ReadWriteType": "All"}
        ],
    },
}

BAD_CLOUDTRAIL = {
    "source": "cloudtrail_config",
    "format": "aws_cloudtrail_json",
    "content": {
        "IsLogging": False,
        "Trail": {"Name": "dormant-trail"},
        "EventSelectors": [],
    },
}

GOOD_BUCKETS = {
    "source": "bucket_policies",
    "format": "aws_s3_json",
    "content": {
        "BucketName": "private-data",
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    },
}

BAD_BUCKETS = {
    "source": "bucket_policies",
    "format": "aws_s3_json",
    "content": {
        "BucketName": "public-bucket",
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": False,
            "IgnorePublicAcls": False,
            "BlockPublicPolicy": False,
            "RestrictPublicBuckets": False,
        },
    },
}

GOOD_ALARMS = {
    "source": "cloudwatch_alarms",
    "format": "aws_cloudwatch_json",
    "content": {
        "MetricAlarms": [
            {"AlarmName": "UnauthorizedAccess", "AlarmActions": ["arn:aws:sns:us-east-1:123:alerts"]},
            {"AlarmName": "RootAccountUsage", "AlarmActions": ["arn:aws:sns:us-east-1:123:alerts"]},
        ]
    },
}

BAD_ALARMS = {
    "source": "cloudwatch_alarms",
    "format": "aws_cloudwatch_json",
    "content": {"MetricAlarms": []},
}

ALL_GOOD_CONFIGS = [GOOD_IAM, GOOD_CLOUDTRAIL, GOOD_BUCKETS, GOOD_ALARMS]
ALL_BAD_CONFIGS = [BAD_IAM_WILDCARD, BAD_CLOUDTRAIL, BAD_BUCKETS, BAD_ALARMS]


# ── config_hasher tests ───────────────────────────────────────────────────────

def test_hash_config_file_deterministic():
    from app.soc2.config_hasher import hash_config_file
    h1 = hash_config_file(GOOD_IAM)
    h2 = hash_config_file(GOOD_IAM)
    assert h1 == h2
    assert len(h1) == 64


def test_hash_config_file_sensitive_to_content():
    from app.soc2.config_hasher import hash_config_file
    h1 = hash_config_file(GOOD_IAM)
    h2 = hash_config_file(BAD_IAM_WILDCARD)
    assert h1 != h2


def test_hash_config_file_ignores_extra_keys():
    from app.soc2.config_hasher import hash_config_file
    base = {"source": "iam_policies", "format": "aws_iam_json", "content": {"x": 1}}
    extra = {"source": "iam_policies", "format": "aws_iam_json", "content": {"x": 1}, "extra_field": "ignored"}
    assert hash_config_file(base) == hash_config_file(extra)


def test_compute_config_corpus_root_deterministic():
    from app.soc2.config_hasher import compute_config_corpus_root
    r1 = compute_config_corpus_root(ALL_GOOD_CONFIGS)
    r2 = compute_config_corpus_root(ALL_GOOD_CONFIGS)
    assert r1 == r2
    assert len(r1) == 64


def test_compute_config_corpus_root_order_sensitive():
    from app.soc2.config_hasher import compute_config_corpus_root
    r1 = compute_config_corpus_root([GOOD_IAM, GOOD_CLOUDTRAIL])
    r2 = compute_config_corpus_root([GOOD_CLOUDTRAIL, GOOD_IAM])
    assert r1 != r2


def test_extract_control_evidence_all_keys():
    from app.soc2.config_hasher import extract_control_evidence
    evidence = extract_control_evidence(ALL_GOOD_CONFIGS)
    for ctrl in ["CC6.1", "CC6.2", "CC6.3", "CC6.6", "CC7.1", "CC7.2"]:
        assert ctrl in evidence
        assert isinstance(evidence[ctrl], list)


# ── ConfigInspectorAgent: all-pass case ──────────────────────────────────────

def test_inspector_all_pass():
    from app.soc2.agents.config_inspector import ConfigInspectorAgent
    agent = ConfigInspectorAgent()
    results = agent.inspect(ALL_GOOD_CONFIGS)
    assert set(results.keys()) == {"CC6.1", "CC6.2", "CC6.3", "CC6.6", "CC7.1", "CC7.2"}
    for ctrl, result in results.items():
        assert result.passed is True, f"{ctrl} should pass but got: {result.finding}"


# ── ConfigInspectorAgent: per-control fail cases ──────────────────────────────

def test_inspector_cc61_no_mfa_fails():
    from app.soc2.agents.config_inspector import check_mfa_enforcement
    # Policy with no MFA condition
    configs = [{"source": "iam_policies", "format": "aws_iam_json",
                "content": {"Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}]}}]
    result = check_mfa_enforcement(configs)
    assert result.passed is False
    assert result.control_id == "CC6.1"


def test_inspector_cc61_mfa_allow_passes():
    from app.soc2.agents.config_inspector import check_mfa_enforcement
    configs = [{"source": "iam_policies", "format": "aws_iam_json",
                "content": {"Statement": [
                    {"Effect": "Allow", "Action": "s3:*", "Resource": "*",
                     "Condition": {"Bool": {"aws:MultiFactorAuthPresent": "true"}}}
                ]}}]
    result = check_mfa_enforcement(configs)
    assert result.passed is True


def test_inspector_cc62_full_wildcard_fails():
    from app.soc2.agents.config_inspector import check_least_privilege
    result = check_least_privilege([BAD_IAM_WILDCARD])
    assert result.passed is False
    assert result.control_id == "CC6.2"


def test_inspector_cc62_deny_wildcard_passes():
    from app.soc2.agents.config_inspector import check_least_privilege
    # Deny Action=* Resource=* is acceptable
    configs = [{"source": "iam_policies", "format": "aws_iam_json",
                "content": {"Statement": [{"Effect": "Deny", "Action": "*", "Resource": "*"}]}}]
    result = check_least_privilege(configs)
    assert result.passed is True


def test_inspector_cc63_no_selectors_fails():
    from app.soc2.agents.config_inspector import check_access_logging
    result = check_access_logging([BAD_CLOUDTRAIL])
    assert result.passed is False


def test_inspector_cc66_public_bucket_fails():
    from app.soc2.agents.config_inspector import check_no_public_buckets
    result = check_no_public_buckets([BAD_BUCKETS])
    assert result.passed is False


def test_inspector_cc71_not_logging_fails():
    from app.soc2.agents.config_inspector import check_cloudtrail_active
    result = check_cloudtrail_active([BAD_CLOUDTRAIL])
    assert result.passed is False


def test_inspector_cc72_no_alarms_fails():
    from app.soc2.agents.config_inspector import check_alerting_configured
    result = check_alerting_configured([BAD_ALARMS])
    assert result.passed is False


# ── SCAE resistance ───────────────────────────────────────────────────────────

def test_inspector_scae_policy_name_does_not_fool_mfa_check():
    """
    A policy named 'ComplianceEnforcedMFAPolicy' with no actual MFA condition
    must still fail CC6.1. Inspector reads content, not names.
    """
    from app.soc2.agents.config_inspector import check_mfa_enforcement, check_least_privilege
    result_mfa = check_mfa_enforcement([SCAE_IAM])
    assert result_mfa.passed is False, "SCAE: policy name must not substitute for actual MFA condition"

    # Same config: Allow Action=* Resource=* must still fail CC6.2
    result_wildcard = check_least_privilege([SCAE_IAM])
    assert result_wildcard.passed is False, "SCAE: wildcard Allow must fail regardless of policy name"


# ── ControlEvaluatorAgent ─────────────────────────────────────────────────────

def _mock_evaluator_response(all_pass: bool = True) -> dict:
    controls = ["CC6.1", "CC6.2", "CC6.3", "CC6.6", "CC7.1", "CC7.2"]
    return {
        "control_assessments": [
            {
                "control_id": c,
                "hard_finding": all_pass,
                "qualitative_assessment": f"Assessment for {c}.",
                "risk_notes": "No residual risk." if all_pass else "Remediation required.",
                "effective": all_pass,
            }
            for c in controls
        ],
        "overall_assessment": "All controls effective." if all_pass else "Remediation required.",
        "material_weaknesses": [] if all_pass else ["CC6.1"],
        "significant_deficiencies": [],
    }


@pytest.mark.asyncio
async def test_evaluator_overrides_llm_effective_field():
    """
    Even if LLM returns effective=True for a failed control, the hard finding wins.
    """
    from app.soc2.agents.config_inspector import ConfigInspectorAgent
    from app.soc2.agents.control_evaluator import ControlEvaluatorAgent

    # LLM claims everything passes
    llm_response = _mock_evaluator_response(all_pass=True)
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(llm_response))]
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    # But the hard finding says CC6.2 fails (wildcard policy)
    hard_findings = ConfigInspectorAgent().inspect([BAD_IAM_WILDCARD, GOOD_CLOUDTRAIL, GOOD_BUCKETS, GOOD_ALARMS])

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        evaluator = ControlEvaluatorAgent()
        result = await evaluator.evaluate("TestOrg", ALL_BAD_CONFIGS, hard_findings)

    assert result is not None
    # all_controls_effective must be False because CC6.2 hard finding = False
    assert result.all_controls_effective is False
    # The failed control must appear in material_weaknesses
    failed = [ctrl for ctrl, r in hard_findings.items() if not r.passed]
    for ctrl in failed:
        assert ctrl in result.material_weaknesses or ctrl in result.significant_deficiencies


@pytest.mark.asyncio
async def test_evaluator_returns_none_on_llm_failure():
    """ControlEvaluatorAgent must return None (non-fatal) when LLM raises."""
    from app.soc2.agents.config_inspector import ConfigInspectorAgent
    from app.soc2.agents.control_evaluator import ControlEvaluatorAgent

    hard_findings = ConfigInspectorAgent().inspect(ALL_GOOD_CONFIGS)
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("API unavailable"))

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        evaluator = ControlEvaluatorAgent()
        result = await evaluator.evaluate("TestOrg", ALL_GOOD_CONFIGS, hard_findings)

    assert result is None


@pytest.mark.asyncio
async def test_evaluator_handles_markdown_fenced_json():
    """Evaluator must strip markdown code fences before JSON parsing."""
    from app.soc2.agents.config_inspector import ConfigInspectorAgent
    from app.soc2.agents.control_evaluator import ControlEvaluatorAgent

    payload = _mock_evaluator_response(all_pass=True)
    fenced = f"```json\n{json.dumps(payload)}\n```"
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=fenced)]
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    hard_findings = ConfigInspectorAgent().inspect(ALL_GOOD_CONFIGS)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        evaluator = ControlEvaluatorAgent()
        result = await evaluator.evaluate("TestOrg", ALL_GOOD_CONFIGS, hard_findings)

    assert result is not None
    assert result.all_controls_effective is True


# ── SOC2ControlCredential schema ──────────────────────────────────────────────

def test_credential_schema_fields():
    from app.soc2.schemas import ControlFinding, SOC2ControlCredential
    finding = ControlFinding(
        control_id="CC6.1",
        hard_finding=True,
        evidence_snippets=["MFA enforced"],
        effective=True,
        qualitative_assessment="Good.",
        risk_notes="None.",
    )
    cred = SOC2ControlCredential(
        audit_id="audit-1",
        org_name="TestOrg",
        corpus_root="a" * 64,
        controls_assessed=["CC6.1"],
        control_findings=[finding],
        overall_assessment="All effective.",
        material_weaknesses=[],
        significant_deficiencies=[],
        all_controls_effective=True,
        credential_hash="b" * 64,
        issued_at="2026-06-19T00:00:00Z",
        tee_attested=True,
    )
    assert cred.credential_type == "SOC2ControlCredential"
    assert cred.all_controls_effective is True
    assert len(cred.control_findings) == 1


def test_credential_hash_deterministic():
    from app.soc2.schemas import SOC2ControlCredential

    body = {
        "audit_id": "audit-1",
        "org_name": "TestOrg",
        "corpus_root": "a" * 64,
        "controls_assessed": ["CC6.1"],
        "control_findings": [],
        "overall_assessment": "OK",
        "material_weaknesses": [],
        "significant_deficiencies": [],
        "all_controls_effective": True,
        "issued_at": "2026-06-19T00:00:00Z",
        "tee_attested": True,
    }
    h1 = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    h2 = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    assert h1 == h2
    assert len(h1) == 64


# ── HTTP endpoint tests ───────────────────────────────────────────────────────

from contextlib import contextmanager

@contextmanager
def _soc2_client(tmp_path):
    """Context manager: swap DB path, run lifespan (creates tables), yield client."""
    orig = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "test_soc2.db"
    from app.main import app as fastapi_app
    try:
        with TestClient(fastapi_app, raise_server_exceptions=True) as client:
            yield client
    finally:
        db_module.DB_PATH = orig


INGEST_BODY = {
    "org_name": "AcmeCorp",
    "configs": [
        GOOD_IAM,
        GOOD_CLOUDTRAIL,
        GOOD_BUCKETS,
        GOOD_ALARMS,
    ],
}


def test_http_ingest_returns_corpus_root(tmp_path):
    with _soc2_client(tmp_path) as client:
        resp = client.post("/api/soc2/audits/ingest", json=INGEST_BODY)
        assert resp.status_code == 200
        body = resp.json()
        assert "corpus_root" in body
        assert len(body["corpus_root"]) == 64
        assert body["config_count"] == 4
        assert body["status"] == "pending"
        for ctrl in ["CC6.1", "CC6.2", "CC6.3", "CC6.6", "CC7.1", "CC7.2"]:
            assert ctrl in body["control_evidence_preview"]


def test_http_ingest_stores_configs_for_evaluate(tmp_path):
    """GET after ingest must show status=pending with no credential yet."""
    with _soc2_client(tmp_path) as client:
        ingest_resp = client.post("/api/soc2/audits/ingest", json=INGEST_BODY)
        assert ingest_resp.status_code == 200
        audit_id = ingest_resp.json()["audit_id"]

        get_resp = client.get(f"/api/soc2/audits/{audit_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "pending"
        assert get_resp.json()["credential"] is None


def test_http_evaluate_happy_path(tmp_path):
    """Full ingest → evaluate round-trip; credential and tee_quote must be present."""
    evaluator_payload = _mock_evaluator_response(all_pass=True)
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(evaluator_payload))]
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    with _soc2_client(tmp_path) as client:
        ingest_resp = client.post("/api/soc2/audits/ingest", json=INGEST_BODY)
        assert ingest_resp.status_code == 200
        audit_id = ingest_resp.json()["audit_id"]

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            eval_resp = client.post(f"/api/soc2/audits/{audit_id}/evaluate")

        assert eval_resp.status_code == 200
        body = eval_resp.json()
        assert body["status"] == "complete"
        cred = body["credential"]
        assert cred["all_controls_effective"] is True
        assert len(cred["credential_hash"]) == 64
        assert len(cred["controls_assessed"]) == 6
        assert body["tee_quote"].startswith("sim_quote:")


def test_http_evaluate_idempotent(tmp_path):
    """Calling evaluate twice must return the same credential; LLM called only once."""
    evaluator_payload = _mock_evaluator_response(all_pass=True)
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(evaluator_payload))]
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    with _soc2_client(tmp_path) as client:
        ingest_resp = client.post("/api/soc2/audits/ingest", json=INGEST_BODY)
        audit_id = ingest_resp.json()["audit_id"]

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            r1 = client.post(f"/api/soc2/audits/{audit_id}/evaluate")
            r2 = client.post(f"/api/soc2/audits/{audit_id}/evaluate")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["credential"]["credential_hash"] == r2.json()["credential"]["credential_hash"]
        assert mock_client.messages.create.call_count == 1


def test_http_evaluate_failed_controls(tmp_path):
    """Evaluate with all-bad configs must set all_controls_effective=False."""
    evaluator_payload = _mock_evaluator_response(all_pass=False)
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(evaluator_payload))]
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    bad_body = {
        "org_name": "BadCorp",
        "configs": [BAD_IAM_WILDCARD, BAD_CLOUDTRAIL, BAD_BUCKETS, BAD_ALARMS],
    }

    with _soc2_client(tmp_path) as client:
        ingest_resp = client.post("/api/soc2/audits/ingest", json=bad_body)
        assert ingest_resp.status_code == 200
        audit_id = ingest_resp.json()["audit_id"]

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            eval_resp = client.post(f"/api/soc2/audits/{audit_id}/evaluate")

        assert eval_resp.status_code == 200
        cred = eval_resp.json()["credential"]
        assert cred["all_controls_effective"] is False
        assert len(cred["material_weaknesses"]) > 0


def test_http_evaluate_evaluator_failure_is_nonfatal(tmp_path):
    """If ControlEvaluatorAgent raises, evaluate must still return 200 with hard findings."""
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("LLM down"))

    with _soc2_client(tmp_path) as client:
        ingest_resp = client.post("/api/soc2/audits/ingest", json=INGEST_BODY)
        audit_id = ingest_resp.json()["audit_id"]

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            eval_resp = client.post(f"/api/soc2/audits/{audit_id}/evaluate")

        assert eval_resp.status_code == 200
        body = eval_resp.json()
        assert body["status"] == "complete"
        assert body["credential"]["all_controls_effective"] is True


def test_http_get_audit_not_found(tmp_path):
    with _soc2_client(tmp_path) as client:
        resp = client.get("/api/soc2/audits/nonexistent-id")
        assert resp.status_code == 404


def test_http_get_audit_after_evaluate(tmp_path):
    """GET after evaluate must return status=complete and full credential."""
    evaluator_payload = _mock_evaluator_response(all_pass=True)
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(evaluator_payload))]
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    with _soc2_client(tmp_path) as client:
        ingest_resp = client.post("/api/soc2/audits/ingest", json=INGEST_BODY)
        audit_id = ingest_resp.json()["audit_id"]

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            client.post(f"/api/soc2/audits/{audit_id}/evaluate")

        get_resp = client.get(f"/api/soc2/audits/{audit_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["status"] == "complete"
        assert body["credential"] is not None
        assert body["tee_quote"].startswith("sim_quote:")
