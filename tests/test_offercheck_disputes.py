"""
Tests for the dispute/contest surface (app.offercheck.disputes) — filed
against an already-AGREED session's outcome. Covers: filing valid process
and outcome disputes, rejecting invalid ones (no referenced_field, an
unavailable referenced_field, a non-party filer, a non-AGREED session, empty/
oversized evidence, a process dispute that wrongly references a field),
confirming filing never mutates any already-attested field, confirming
disputes surface via the live disputes_view (not the original attested
quote), and multiple disputes of both types from both parties coexisting.
Follows tests/test_offercheck_approval.py's fixture conventions (own
_new_session/_agreed_session helpers, autouse state-reset fixture).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.offercheck import disputes, invites, negotiation, rate_limit, store, verifier
from app.offercheck.schemas import CompetingOffer


@pytest.fixture(autouse=True)
def _clear_state():
    store.reset()
    rate_limit.reset()
    invites.reset()
    yield
    store.reset()
    rate_limit.reset()
    invites.reset()


def _plausible_offer(**overrides):
    defaults = dict(
        company="Stripe", role="Senior Software Engineer", base_salary=180_000,
        equity_value=40_000, bonus=15_000, start_date="2026-09-01",
    )
    defaults.update(overrides)
    return CompetingOffer(**defaults)


def _new_session(candidate_ask=185_000.0):
    consistency = verifier.check_consistency(_plausible_offer(), candidate_ask)
    return store.create_session(_plausible_offer(), candidate_ask, consistency)


def _agreed_session(candidate_ask=185_000.0, market_percentile=None):
    """AGREED session with a real employer counter (so final_gap_pct is non-None,
    agreed_price=177_000) and an optionally pre-set market_percentile — dispute
    tests don't need to exercise the real BLS/ONS fetch, just a session where that
    field is either populated or (by default) None, matching "lookup never
    succeeded" — see tests/test_offercheck.py for market_data fetch coverage."""
    session = _new_session(candidate_ask)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="counter", value=170_000.0)
    negotiation.apply_move(session, actor="candidate", move="counter", value=180_000.0)
    negotiation.apply_move(session, actor="employer", move="counter", value=177_000.0)
    negotiation.apply_move(session, actor="candidate", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    assert session.state == "AGREED"
    assert session.agreed_price == 177_000.0
    session.market_percentile = market_percentile
    return session


# ---------------------------------------------------------------------------
# file_dispute() — valid filings
# ---------------------------------------------------------------------------

def test_file_valid_process_dispute():
    session = _agreed_session()
    dispute = disputes.file_dispute(
        session, filed_by="candidate", dispute_type="process",
        evidence="The employer countered after I had already accepted in round 3.",
    )
    assert dispute.dispute_type == "process"
    assert dispute.filed_by == "candidate"
    assert dispute.referenced_field is None
    assert dispute.dispute_hash  # non-empty
    assert session.disputes == [dispute]


def test_file_valid_outcome_dispute_referencing_final_gap_pct():
    session = _agreed_session()
    dispute = disputes.file_dispute(
        session, filed_by="employer", dispute_type="outcome",
        evidence="The final price barely moved from my opening counter — this doesn't feel negotiated.",
        referenced_field="final_gap_pct",
    )
    assert dispute.dispute_type == "outcome"
    assert dispute.referenced_field == "final_gap_pct"
    assert dispute in session.disputes


def test_file_valid_outcome_dispute_referencing_market_percentile():
    session = _agreed_session(market_percentile=12.5)
    dispute = disputes.file_dispute(
        session, filed_by="candidate", dispute_type="outcome",
        evidence="12.5th percentile is well below market for this role.",
        referenced_field="market_percentile",
    )
    assert dispute.referenced_field == "market_percentile"
    assert dispute in session.disputes


def test_dispute_hash_is_deterministic_and_covers_disclosed_fields():
    session = _agreed_session()
    dispute = disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence="Round count seems wrong.")
    from app.offercheck.disputes import _hash_dispute
    assert dispute.dispute_hash == _hash_dispute(dispute)


# ---------------------------------------------------------------------------
# file_dispute() — rejections
# ---------------------------------------------------------------------------

def test_outcome_dispute_without_referenced_field_is_rejected():
    session = _agreed_session()
    with pytest.raises(disputes.ReferencedFieldRequired):
        disputes.file_dispute(session, filed_by="candidate", dispute_type="outcome", evidence="This seems unfair.")


def test_outcome_dispute_referencing_unknown_field_is_rejected():
    session = _agreed_session()
    with pytest.raises(disputes.UnknownReferencedField):
        disputes.file_dispute(
            session, filed_by="candidate", dispute_type="outcome",
            evidence="Disputing the base salary directly.", referenced_field="agreed_price",
        )


def test_outcome_dispute_referencing_none_valued_field_is_rejected():
    """market_percentile is None on this session (the lookup never succeeded) —
    can't dispute a value that was never computed."""
    session = _agreed_session(market_percentile=None)
    with pytest.raises(disputes.ReferencedFieldUnavailable):
        disputes.file_dispute(
            session, filed_by="candidate", dispute_type="outcome",
            evidence="Below market.", referenced_field="market_percentile",
        )


def test_process_dispute_with_a_referenced_field_is_rejected():
    session = _agreed_session()
    with pytest.raises(disputes.ReferencedFieldNotAllowedForProcess):
        disputes.file_dispute(
            session, filed_by="candidate", dispute_type="process",
            evidence="Something about process.", referenced_field="final_gap_pct",
        )


def test_dispute_filed_by_non_party_is_rejected():
    session = _agreed_session()
    with pytest.raises(disputes.NotAParty):
        disputes.file_dispute(session, filed_by="mediator", dispute_type="process", evidence="Not a real party.")


# ---------------------------------------------------------------------------
# Per-session-per-party dispute cap (MAX_DISPUTES_PER_PARTY_PER_SESSION)
# ---------------------------------------------------------------------------

def test_filing_up_to_the_cap_succeeds_each_time():
    session = _agreed_session()
    for i in range(disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION):
        dispute = disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence=f"Complaint number {i}.")
        assert dispute in session.disputes
    assert len(session.disputes) == disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION


def test_filing_over_the_cap_is_rejected():
    session = _agreed_session()
    for i in range(disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION):
        disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence=f"Complaint number {i}.")
    with pytest.raises(disputes.DisputeLimitExceeded):
        disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence="One too many.")
    # the rejected attempt was never recorded
    assert len(session.disputes) == disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION


def test_cap_is_per_party_not_shared_across_the_session():
    """The employer hitting their cap must not block the candidate from filing
    their own disputes on the same session, and vice versa."""
    session = _agreed_session()
    for i in range(disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION):
        disputes.file_dispute(session, filed_by="employer", dispute_type="process", evidence=f"Employer complaint {i}.")
    with pytest.raises(disputes.DisputeLimitExceeded):
        disputes.file_dispute(session, filed_by="employer", dispute_type="process", evidence="Employer over cap.")

    # Candidate's own bucket is completely untouched.
    for i in range(disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION):
        dispute = disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence=f"Candidate complaint {i}.")
        assert dispute in session.disputes
    assert len(session.disputes) == 2 * disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION


def test_cap_is_per_session_not_shared_across_sessions():
    """The same party filing up to their cap on one session must not affect
    their ability to file on a completely different session."""
    session_a = _agreed_session()
    session_b = _agreed_session()
    for i in range(disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION):
        disputes.file_dispute(session_a, filed_by="candidate", dispute_type="process", evidence=f"Complaint {i} on A.")
    with pytest.raises(disputes.DisputeLimitExceeded):
        disputes.file_dispute(session_a, filed_by="candidate", dispute_type="process", evidence="Over cap on A.")

    # Session B's bucket for the same party is untouched.
    dispute_b = disputes.file_dispute(session_b, filed_by="candidate", dispute_type="process", evidence="First complaint on B.")
    assert dispute_b in session_b.disputes
    assert len(session_b.disputes) == 1


def test_dispute_on_non_agreed_session_is_rejected():
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="walk", value=None)
    assert session.state == "WALKAWAY"
    with pytest.raises(disputes.SessionNotAgreed):
        disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence="Walked away unfairly.")


def test_dispute_on_pending_approval_session_is_rejected():
    """Not yet AGREED — still mid-approval, not just some other terminal state."""
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)
    assert session.state == "PENDING_APPROVAL"
    with pytest.raises(disputes.SessionNotAgreed):
        disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence="Too early to dispute.")


def test_empty_evidence_is_rejected():
    session = _agreed_session()
    with pytest.raises(disputes.InvalidEvidence):
        disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence="   ")


def test_oversized_evidence_is_rejected():
    session = _agreed_session()
    with pytest.raises(disputes.InvalidEvidence):
        disputes.file_dispute(
            session, filed_by="candidate", dispute_type="process",
            evidence="x" * (disputes.EVIDENCE_MAX_LENGTH + 1),
        )


def test_unknown_dispute_type_is_rejected():
    session = _agreed_session()
    with pytest.raises(disputes.DisputeError):
        disputes.file_dispute(session, filed_by="candidate", dispute_type="vibes", evidence="Just a feeling.")


# ---------------------------------------------------------------------------
# Filing does not mutate any already-attested field
# ---------------------------------------------------------------------------

def test_filing_a_dispute_does_not_change_agreed_price_or_attested_fields():
    session = _agreed_session(market_percentile=42.0)
    original_agreed_price = session.agreed_price
    original_final_gap_pct = negotiation.final_gap_pct(session)
    original_market_percentile = session.market_percentile
    original_state = session.state
    original_terms = negotiation.attested_terms(session)

    disputes.file_dispute(
        session, filed_by="candidate", dispute_type="outcome",
        evidence="Disputing the outcome.", referenced_field="market_percentile",
    )
    disputes.file_dispute(session, filed_by="employer", dispute_type="process", evidence="Disputing the process.")

    assert session.agreed_price == original_agreed_price
    assert negotiation.final_gap_pct(session) == original_final_gap_pct
    assert session.market_percentile == original_market_percentile
    assert session.state == original_state  # still AGREED — no DISPUTED state, no reopen
    # attested_terms() itself is also unaffected by disputes (see disputes.py docstring —
    # it deliberately doesn't read session.disputes at all)
    new_terms = negotiation.attested_terms(session)
    assert new_terms == original_terms


def test_filing_a_dispute_does_not_touch_reopen_mechanism_fields():
    """The core decoupling guarantee: filing must never touch extension_count,
    max_rounds, or the approval-vote fields the reopen path uses."""
    session = _agreed_session()
    original_extension_count = session.extension_count
    original_max_rounds = session.max_rounds
    original_candidate_vote = session.candidate_approval_vote
    original_employer_vote = session.employer_approval_vote

    disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence="Something happened.")

    assert session.extension_count == original_extension_count
    assert session.max_rounds == original_max_rounds
    assert session.candidate_approval_vote == original_candidate_vote
    assert session.employer_approval_vote == original_employer_vote


# ---------------------------------------------------------------------------
# disputes_view() — the live, separate view (not the original attested quote)
# ---------------------------------------------------------------------------

def test_disputes_appear_in_disputes_view():
    session = _agreed_session(market_percentile=42.0)
    dispute = disputes.file_dispute(
        session, filed_by="candidate", dispute_type="outcome",
        evidence="Below market.", referenced_field="market_percentile",
    )
    view = disputes.disputes_view(session)
    assert view["agreed_price"] == session.agreed_price
    assert view["final_gap_pct"] == negotiation.final_gap_pct(session)
    assert view["market_percentile"] == 42.0
    assert len(view["disputes"]) == 1
    assert view["disputes"][0]["dispute_id"] == dispute.dispute_id
    assert view["disputes"][0]["dispute_hash"] == dispute.dispute_hash


def test_disputes_view_empty_before_any_filing():
    session = _agreed_session()
    view = disputes.disputes_view(session)
    assert view["disputes"] == []


def test_multiple_disputes_of_both_types_from_both_parties_coexist():
    session = _agreed_session(market_percentile=60.0)
    d1 = disputes.file_dispute(session, filed_by="candidate", dispute_type="process", evidence="Process complaint one.")
    d2 = disputes.file_dispute(
        session, filed_by="employer", dispute_type="outcome",
        evidence="Outcome complaint.", referenced_field="final_gap_pct",
    )
    d3 = disputes.file_dispute(
        session, filed_by="candidate", dispute_type="outcome",
        evidence="Another outcome complaint.", referenced_field="market_percentile",
    )
    d4 = disputes.file_dispute(session, filed_by="employer", dispute_type="process", evidence="Process complaint two.")

    assert session.disputes == [d1, d2, d3, d4]
    assert {d.dispute_id for d in session.disputes} == {d1.dispute_id, d2.dispute_id, d3.dispute_id, d4.dispute_id}  # all unique
    view = disputes.disputes_view(session)
    assert len(view["disputes"]) == 4
    filers = {d["filed_by"] for d in view["disputes"]}
    types = {d["dispute_type"] for d in view["disputes"]}
    assert filers == {"candidate", "employer"}
    assert types == {"process", "outcome"}


# ---------------------------------------------------------------------------
# HTTP e2e
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _no_network_market_data_ctx():
    """Blocks the real BLS/ONS HTTP call routes.py::_maybe_attest fires on AGREED
    (see app.offercheck.integrations.market_data) — dispute tests don't exercise
    market_data itself (see tests/test_offercheck.py for that), so this just makes
    the lookup fail fast and non-fatally instead of hitting the real network."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(side_effect=Exception("no network in tests"))
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return patch("httpx.AsyncClient", return_value=ctx)


def _negotiate_to_agreed(client) -> dict:
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {
                "company": "Stripe", "role": "Senior Software Engineer", "base_salary": 165_000,
                "equity_value": 40_000, "bonus": 15_000, "start_date": "2026-09-01",
            },
            "candidate_ask": 185_000,
        },
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155_000, "band_mid": 175_000, "band_max": 195_000},
    )
    # Employer counters at least once so opening_employer_offer (and therefore
    # final_gap_pct) is non-None — an immediate accept never sets it, see
    # negotiation.apply_move, which would make the final_gap_pct outcome-dispute
    # test below reject with ReferencedFieldUnavailable instead of succeeding.
    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "counter", "value": 170_000},
    )
    with _no_network_market_data_ctx():
        client.post(f"/api/offercheck/sessions/{session_id}/candidate/move", json={"token": candidate_token, "move": "accept"})
        client.post(f"/api/offercheck/sessions/{session_id}/employer/approval", json={"token": employer_token, "decision": "approve"})
        client.post(f"/api/offercheck/sessions/{session_id}/candidate/approval", json={"token": candidate_token, "decision": "approve"})

    return {"session_id": session_id, "candidate_token": candidate_token, "employer_token": employer_token}


def test_e2e_file_and_view_disputes(client):
    ids = _negotiate_to_agreed(client)
    session_id, candidate_token, employer_token = ids["session_id"], ids["candidate_token"], ids["employer_token"]

    before = client.get(f"/api/offercheck/sessions/{session_id}/attest", params={"token": candidate_token})
    assert before.status_code == 200
    original_agreed_price = before.json()["agreed_price"]

    process_resp = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/dispute",
        json={"token": employer_token, "dispute_type": "process", "evidence": "Round count in the receipt looks off to me."},
    )
    assert process_resp.status_code == 201
    assert process_resp.json()["filed_by"] == "employer"
    assert process_resp.json()["dispute_type"] == "process"

    outcome_resp = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/dispute",
        json={
            "token": candidate_token, "dispute_type": "outcome",
            "evidence": "The final gap barely moved from the opening counter.", "referenced_field": "final_gap_pct",
        },
    )
    assert outcome_resp.status_code == 201
    assert outcome_resp.json()["filed_by"] == "candidate"
    assert outcome_resp.json()["referenced_field"] == "final_gap_pct"

    view = client.get(f"/api/offercheck/sessions/{session_id}/disputes", params={"token": employer_token})
    assert view.status_code == 200
    body = view.json()
    assert body["agreed_price"] == original_agreed_price
    assert len(body["disputes"]) == 2
    assert {d["filed_by"] for d in body["disputes"]} == {"candidate", "employer"}

    # the original attestation receipt is untouched by the disputes filed above
    after = client.get(f"/api/offercheck/sessions/{session_id}/attest", params={"token": candidate_token})
    assert after.json()["agreed_price"] == original_agreed_price
    assert after.json() == before.json()


def test_e2e_dispute_rejects_invalid_token(client):
    ids = _negotiate_to_agreed(client)
    resp = client.post(
        f"/api/offercheck/sessions/{ids['session_id']}/employer/dispute",
        json={"token": "not-a-real-token", "dispute_type": "process", "evidence": "x"},
    )
    assert resp.status_code == 403


def test_e2e_dispute_rejects_before_agreed(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {
                "company": "Stripe", "role": "Senior Software Engineer", "base_salary": 165_000,
                "equity_value": 40_000, "bonus": 15_000, "start_date": "2026-09-01",
            },
            "candidate_ask": 185_000,
        },
    )
    body = submit.json()
    session_id, candidate_token = body["session_id"], body["candidate_token"]

    resp = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/dispute",
        json={"token": candidate_token, "dispute_type": "process", "evidence": "Too early."},
    )
    assert resp.status_code == 409


def test_e2e_outcome_dispute_rejects_missing_referenced_field(client):
    ids = _negotiate_to_agreed(client)
    resp = client.post(
        f"/api/offercheck/sessions/{ids['session_id']}/employer/dispute",
        json={"token": ids["employer_token"], "dispute_type": "outcome", "evidence": "Bad outcome."},
    )
    assert resp.status_code == 400


def test_e2e_dispute_over_per_session_cap_returns_429(client):
    ids = _negotiate_to_agreed(client)
    session_id, employer_token = ids["session_id"], ids["employer_token"]

    for i in range(disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION):
        resp = client.post(
            f"/api/offercheck/sessions/{session_id}/employer/dispute",
            json={"token": employer_token, "dispute_type": "process", "evidence": f"Complaint {i}."},
        )
        assert resp.status_code == 201

    blocked = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/dispute",
        json={"token": employer_token, "dispute_type": "process", "evidence": "One too many."},
    )
    assert blocked.status_code == 429

    # the candidate's own bucket on the same session is untouched
    candidate_resp = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/dispute",
        json={"token": ids["candidate_token"], "dispute_type": "process", "evidence": "Candidate's own complaint."},
    )
    assert candidate_resp.status_code == 201
