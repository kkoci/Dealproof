"""
Tests for Offer Check Phase 5 (vertical/hr-offer-check branch): the training-data
export pipeline (app.offercheck.export) — see that module's own docstring for the
full anonymization policy this enforces. The central thing every test in the
"anonymization" section below checks is a negative: that a specific real-looking
value (a company name, free-text priorities, an ATS ref, a token) never appears
anywhere in the exported record — not just that the expected fields are present.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.offercheck import export, negotiation, package, store, verifier
from app.offercheck.schemas import CompetingOffer, OfferPackage

pytestmark = []


@pytest.fixture(autouse=True)
def _clear_store():
    store.reset()
    yield
    store.reset()


def _offer(**overrides):
    defaults = dict(
        company="Very Identifiable Company Inc", role="Senior Software Engineer", base_salary=180_000,
        equity_value=40_000, bonus=15_000, start_date="2026-09-01",
        location="Seattle, WA", currency="USD",
    )
    defaults.update(overrides)
    return CompetingOffer(**defaults)


def _agreed_session(**offer_overrides):
    offer = _offer(**offer_overrides)
    consistency = verifier.check_consistency(offer, 185_000)
    session = store.create_session(
        offer, 185_000, consistency,
        company_id="company-xyz-123",
        ats_candidate_ref="greenhouse-candidate-456",
        candidate_priorities="I currently work at Acme Corp and my manager is Jane Doe",
    )
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="counter", value=170_000)
    negotiation.apply_move(session, actor="candidate", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    assert session.state == "AGREED"
    return session


def _non_terminal_session():
    offer = _offer()
    consistency = verifier.check_consistency(offer, 185_000)
    session = store.create_session(offer, 185_000, consistency)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    return session


def _walkaway_session():
    offer = _offer(company="Some Other Real Company LLC")
    consistency = verifier.check_consistency(offer, 185_000)
    session = store.create_session(offer, 185_000, consistency)
    negotiation.set_employer_band(session, 100_000, 110_000, 120_000)
    negotiation.apply_move(session, actor="employer", move="walk", value=None)
    return session


def _package_agreed_session():
    offer = _offer(company="Package Mode Real Company Ltd", role="Staff Engineer")
    consistency = verifier.check_consistency(offer, 220_000)
    session = store.create_session(offer, 220_000, consistency)
    negotiation.set_employer_band(session, 190_000, 210_000, 230_000)
    opening = OfferPackage(base=205_000, equity_grant=70_000).model_dump()
    package.apply_package_move(session, actor="employer", move="counter", package=opening)
    package.apply_package_move(session, actor="candidate", move="accept", package=None)
    package.apply_package_approval_vote(session, actor="employer", decision="approve")
    package.apply_package_approval_vote(session, actor="candidate", decision="approve")
    assert session.package_state == "AGREED"
    return session


# ---------------------------------------------------------------------------
# Correctness
# ---------------------------------------------------------------------------

def test_export_non_terminal_session_returns_none():
    session = _non_terminal_session()
    assert export.export_session(session) is None


def test_export_agreed_scalar_session_shape():
    session = _agreed_session()
    record = export.export_session(session)
    assert record["status"] == "completed"
    assert record["mode"] == "scalar"
    assert record["role_category"] == "Senior Software Engineer"
    assert record["location"] == "Seattle, WA"
    assert record["currency"] == "USD"
    assert record["final_solution"] == 170_000
    assert len(record["rounds"]) == 2
    assert record["rounds"][0] == {"round": 1, "actor": "employer", "move": "counter", "value": 170_000}
    assert record["final_gap_pct"] is not None


def test_export_walkaway_session_is_aborted_with_no_final_solution():
    session = _walkaway_session()
    record = export.export_session(session)
    assert record["status"] == "aborted"
    assert record["final_solution"] is None
    assert record["final_gap_pct"] is None
    assert len(record["rounds"]) == 1
    assert record["rounds"][0]["move"] == "walk"


def test_export_package_session_shape():
    session = _package_agreed_session()
    record = export.export_session(session)
    assert record["mode"] == "package"
    assert record["status"] == "completed"
    assert record["final_solution"]["base"] == 205_000.0
    assert record["final_total_comp"] is not None
    assert set(record["dimensions"].keys()) == {
        "base", "equity_grant", "vesting_years", "cliff_months", "signing_bonus",
        "annual_bonus_pct", "remote", "start_date_days", "pto_days",
    }


def test_export_id_is_stable_and_not_the_raw_session_id():
    session = _agreed_session()
    record1 = export.export_session(session)
    record2 = export.export_session(session)
    assert record1["id"] == record2["id"]  # stable across calls
    assert record1["id"] != session.id


def test_export_sessions_skips_non_terminal_and_keeps_terminal():
    sessions = [_agreed_session(), _non_terminal_session(), _walkaway_session()]
    records = export.export_sessions(sessions)
    assert len(records) == 2
    assert {r["status"] for r in records} == {"completed", "aborted"}


# ---------------------------------------------------------------------------
# Anonymization — negative assertions: these specific strings must NEVER appear
# ---------------------------------------------------------------------------

def test_export_never_includes_company_name():
    session = _agreed_session()
    record = export.export_session(session)
    dumped = json.dumps(record)
    assert "Very Identifiable Company Inc" not in dumped
    assert session.competing_offer.company not in dumped


def test_export_never_includes_free_text_priorities():
    session = _agreed_session()
    record = export.export_session(session)
    dumped = json.dumps(record)
    assert "Acme Corp" not in dumped
    assert "Jane Doe" not in dumped
    assert "candidate_priorities" not in record


def test_export_never_includes_ats_candidate_ref():
    session = _agreed_session()
    record = export.export_session(session)
    dumped = json.dumps(record)
    assert "greenhouse-candidate-456" not in dumped
    assert "ats_candidate_ref" not in record


def test_export_never_includes_company_id():
    session = _agreed_session()
    record = export.export_session(session)
    dumped = json.dumps(record)
    assert "company-xyz-123" not in dumped
    assert "company_id" not in record


def test_export_never_includes_party_tokens():
    session = _agreed_session()
    record = export.export_session(session)
    dumped = json.dumps(record)
    assert session.candidate_token not in dumped
    assert session.employer_token not in dumped


def test_export_never_includes_a_utilities_block():
    """Structural honesty check — see export.py's own module docstring on why
    real per-party utility weights are never fabricated."""
    session = _agreed_session()
    record = export.export_session(session)
    assert "utilities" not in record
    for spec in record["dimensions"].values():
        assert "weight" not in spec


# ---------------------------------------------------------------------------
# store.all_sessions() — used by the admin export route
# ---------------------------------------------------------------------------

def test_all_sessions_returns_every_session():
    a, b = _agreed_session(), _walkaway_session()
    all_ids = {s.id for s in store.all_sessions()}
    assert {a.id, b.id} <= all_ids


# ---------------------------------------------------------------------------
# HTTP e2e — admin export route
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_export_route_requires_internal_key(client):
    resp = client.get("/api/offercheck/admin/export-training-data")
    assert resp.status_code == 401


def test_export_route_rejects_wrong_internal_key(client):
    from unittest.mock import patch
    with patch("app.offercheck.routes.settings.offercheck_internal_key", "real-secret"):
        resp = client.get("/api/offercheck/admin/export-training-data", headers={"X-Internal-Key": "wrong"})
    assert resp.status_code == 401


def test_export_route_returns_anonymized_records(client):
    from unittest.mock import patch
    session = _agreed_session()
    with patch("app.offercheck.routes.settings.offercheck_internal_key", "real-secret"):
        resp = client.get("/api/offercheck/admin/export-training-data", headers={"X-Internal-Key": "real-secret"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    dumped = json.dumps(body)
    assert "Very Identifiable Company Inc" not in dumped
    assert session.id not in dumped
