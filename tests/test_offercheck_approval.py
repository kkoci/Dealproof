"""
Tests for the PENDING_APPROVAL stage — the one human touchpoint inserted between an
"accept" and a genuinely terminal AGREED (see app.offercheck.negotiation's module
docstring). Covers the resolution rule (both approve / one declines / one requests
more rounds then both approve / extension cap exhausted / decline-wins tie-break),
the reopen turn-assignment rule, attestation timing, and package-mode parity.
"""
import pytest
from fastapi.testclient import TestClient

from app.offercheck import credential, demo_auth, invites, negotiation, package, rate_limit, store, verifier
from app.offercheck.schemas import CompetingOffer

pytestmark = []


@pytest.fixture(autouse=True)
def _clear_state():
    store.reset()
    rate_limit.reset()
    invites.reset()
    demo_auth.reset()
    yield
    store.reset()
    rate_limit.reset()
    invites.reset()
    demo_auth.reset()


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


def _accepted_session(candidate_ask=185_000.0, actor="employer"):
    """A session sitting at PENDING_APPROVAL, ready for approval votes."""
    session = _new_session(candidate_ask)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor=actor, move="accept", value=None)
    assert session.state == "PENDING_APPROVAL"
    return session


def _package(**overrides):
    defaults = dict(
        base=180_000.0, equity_grant=0.0, vesting_years=4.0, cliff_months=12.0,
        signing_bonus=0.0, annual_bonus_pct=0.0, remote="hybrid", start_date_days=30.0, pto_days=15.0,
    )
    defaults.update(overrides)
    return defaults


def _sealed_package_session(candidate_total_comp_floor=150_000.0, employer_total_comp_budget=300_000.0):
    consistency = verifier.check_consistency(_plausible_offer(), 190_000.0)
    session = store.create_session(
        _plausible_offer(), 190_000.0, consistency,
        candidate_package_ask=_package(base=190_000), candidate_total_comp_floor=candidate_total_comp_floor,
    )
    negotiation.set_employer_band(session, 155_000, 175_000, 200_000)
    session.employer_total_comp_budget = employer_total_comp_budget
    return session


def _accepted_package_session(actor="employer"):
    session = _sealed_package_session()
    package.apply_package_move(session, actor="employer", move="counter", package=_package(base=185_000))
    if actor == "employer":
        # Employer's own turn to accept only comes back around after candidate counters too.
        package.apply_package_move(session, actor="candidate", move="counter", package=_package(base=183_000))
    package.apply_package_move(session, actor=actor, move="accept", package=None)
    assert session.package_state == "PENDING_APPROVAL"
    return session


# ---------------------------------------------------------------------------
# Pure state-machine — scalar
# ---------------------------------------------------------------------------

def test_both_approve_reaches_agreed():
    session = _accepted_session()
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    assert session.state == "PENDING_APPROVAL"  # only one side voted so far
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    assert session.state == "AGREED"
    assert session.agreed_price == 185_000.0


def test_single_decline_resolves_immediately_without_waiting_for_other_side():
    session = _accepted_session()
    negotiation.apply_approval_vote(session, actor="employer", decision="decline")
    assert session.state == "DECLINED"  # resolved on the first vote alone
    assert session.candidate_approval_vote is None  # candidate never got a chance to vote


def test_decline_wins_regardless_of_which_side_declines():
    for decliner in ("employer", "candidate"):
        session = _accepted_session()
        negotiation.apply_approval_vote(session, actor=decliner, decision="decline")
        assert session.state == "DECLINED"


def test_declined_clears_agreed_price():
    session = _accepted_session()
    assert session.agreed_price == 185_000.0
    negotiation.apply_approval_vote(session, actor="candidate", decision="decline")
    assert session.state == "DECLINED"
    assert session.agreed_price is None


def test_request_more_rounds_then_both_approve_reaches_agreed():
    session = _accepted_session()
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="request_more_rounds")
    # Reopened: extension consumed, votes cleared, negotiation resumes.
    assert session.state in ("EMPLOYER_RESPONDED", "CANDIDATE_COUNTERED")
    assert session.extension_count == 1
    assert session.candidate_approval_vote is None
    assert session.employer_approval_vote is None
    assert session.max_rounds > 5

    # Negotiate one more round and accept again.
    turn = negotiation.current_turn(session)
    negotiation.apply_move(session, actor=turn, move="counter", value=180_000.0)
    other = "candidate" if turn == "employer" else "employer"
    negotiation.apply_move(session, actor=other, move="accept", value=None)
    assert session.state == "PENDING_APPROVAL"

    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    assert session.state == "AGREED"


def test_reopen_gives_the_next_move_to_the_side_that_did_not_request_it():
    """Confirmed design: 'the side that did NOT request the extension gets the next move.'"""
    session = _accepted_session()  # employer accepted -> PENDING_APPROVAL
    negotiation.apply_approval_vote(session, actor="candidate", decision="request_more_rounds")
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    # Candidate asked for more rounds -> employer (the non-requester) moves next.
    assert negotiation.current_turn(session) == "employer"


def test_reopen_gives_the_next_move_to_the_other_non_requester_side_too():
    session = _accepted_session()
    negotiation.apply_approval_vote(session, actor="employer", decision="request_more_rounds")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    # Employer asked for more rounds -> candidate (the non-requester) moves next.
    assert negotiation.current_turn(session) == "candidate"


def test_opening_employer_offer_survives_a_reopen_untouched():
    """A reopen (request_more_rounds) resets votes/turn/max_rounds but must NOT reset or
    re-snapshot opening_employer_offer — it stays pinned to the employer's true first
    counter even if the employer counters again, at a different value, after reopening."""
    session = _new_session(candidate_ask=185_000.0)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)

    negotiation.apply_move(session, actor="employer", move="counter", value=170_000.0)
    assert session.opening_employer_offer == 170_000.0

    negotiation.apply_move(session, actor="candidate", move="counter", value=180_000.0)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)
    assert session.state == "PENDING_APPROVAL"

    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="request_more_rounds")
    assert session.state == "CANDIDATE_COUNTERED"  # reopened; employer (non-requester) moves next
    assert session.opening_employer_offer == 170_000.0  # untouched by the reopen itself

    # Employer counters again post-reopen, at a DIFFERENT value than their original opening —
    # this must not overwrite opening_employer_offer, since it isn't their FIRST counter.
    negotiation.apply_move(session, actor="employer", move="counter", value=172_000.0)
    assert session.opening_employer_offer == 170_000.0
    assert session.employer_current_offer == 172_000.0

    negotiation.apply_move(session, actor="candidate", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")

    assert session.state == "AGREED"
    assert session.agreed_price == 172_000.0
    assert session.opening_employer_offer == 170_000.0  # still the original anchor, not the reopened value
    expected = (172_000.0 - 170_000.0) / 170_000.0 * 100
    assert negotiation.final_gap_pct(session) == pytest.approx(expected)
    assert negotiation.attested_terms(session)["final_gap_pct"] == pytest.approx(expected)


def test_opening_employer_offer_set_by_first_real_counter_even_after_an_immediate_accept():
    """Employer's first move is an immediate accept (no counter at all) -> opening_employer_offer
    stays None. If the session later reopens and the employer counters for the first time ever,
    THAT becomes the anchor — there was no earlier counter to have captured instead."""
    session = _accepted_session(actor="employer")  # employer's only move so far was "accept"
    assert session.opening_employer_offer is None

    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="request_more_rounds")
    assert negotiation.current_turn(session) == "employer"
    assert session.opening_employer_offer is None  # still never countered

    negotiation.apply_move(session, actor="employer", move="counter", value=180_000.0)
    assert session.opening_employer_offer == 180_000.0  # first-ever employer counter, captured now

    negotiation.apply_move(session, actor="candidate", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")

    assert session.state == "AGREED"
    assert session.agreed_price == 180_000.0
    assert session.opening_employer_offer == 180_000.0
    assert negotiation.final_gap_pct(session) == pytest.approx(0.0)


def test_extension_cap_exhausted_reaches_stalemate():
    session = _accepted_session()
    for _ in range(negotiation.MAX_EXTENSIONS):
        negotiation.apply_approval_vote(session, actor="employer", decision="approve")
        negotiation.apply_approval_vote(session, actor="candidate", decision="request_more_rounds")
        assert session.state != "STALEMATE"
        turn = negotiation.current_turn(session)
        negotiation.apply_move(session, actor=turn, move="counter", value=180_000.0)
        other = "candidate" if turn == "employer" else "employer"
        negotiation.apply_move(session, actor=other, move="accept", value=None)
        assert session.state == "PENDING_APPROVAL"

    assert session.extension_count == negotiation.MAX_EXTENSIONS
    # One more request_more_rounds now that the cap is exhausted -> STALEMATE, not another reopen.
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="request_more_rounds")
    assert session.state == "STALEMATE"
    assert session.agreed_price is None


def test_already_voted_raises():
    session = _accepted_session()
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    with pytest.raises(negotiation.AlreadyVoted):
        negotiation.apply_approval_vote(session, actor="employer", decision="approve")


def test_not_pending_approval_raises():
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    with pytest.raises(negotiation.NotPendingApproval):
        negotiation.apply_approval_vote(session, actor="employer", decision="approve")


def test_walkaway_and_expired_unaffected_by_approval_stage():
    """WALKAWAY and EXPIRED are unaffected — reached directly, never gated by PENDING_APPROVAL."""
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="walk", value=None)
    assert session.state == "WALKAWAY"

    session2 = _new_session()
    negotiation.set_employer_band(session2, 155_000, 175_000, 195_000)
    for i in range(5):
        actor = "employer" if i % 2 == 0 else "candidate"
        negotiation.apply_move(session2, actor=actor, move="counter", value=170_000.0 + i)
    assert session2.state == "EXPIRED"


# ---------------------------------------------------------------------------
# Attestation / credential — DECLINED and STALEMATE use the existing default,
# no special-casing, same as WALKAWAY/EXPIRED today.
# ---------------------------------------------------------------------------

def test_credential_computes_for_declined_outcome_with_no_special_casing():
    session = _accepted_session()
    negotiation.apply_approval_vote(session, actor="employer", decision="decline")
    assert session.state == "DECLINED"
    cred = credential.compute_credential(session)
    assert cred.outcome == "declined"


def test_credential_computes_for_stalemate_outcome_with_no_special_casing():
    session = _accepted_session()
    for _ in range(negotiation.MAX_EXTENSIONS):
        negotiation.apply_approval_vote(session, actor="employer", decision="approve")
        negotiation.apply_approval_vote(session, actor="candidate", decision="request_more_rounds")
        turn = negotiation.current_turn(session)
        negotiation.apply_move(session, actor=turn, move="counter", value=180_000.0)
        other = "candidate" if turn == "employer" else "employer"
        negotiation.apply_move(session, actor=other, move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="request_more_rounds")
    assert session.state == "STALEMATE"
    cred = credential.compute_credential(session)
    assert cred.outcome == "stalemate"


def test_attested_terms_reflects_declined_state():
    session = _accepted_session()
    negotiation.apply_approval_vote(session, actor="candidate", decision="decline")
    terms = negotiation.attested_terms(session)
    assert terms["state"] == "DECLINED"
    assert terms["agreed_price"] is None


# ---------------------------------------------------------------------------
# Package mode parity
# ---------------------------------------------------------------------------

def test_package_both_approve_reaches_agreed():
    session = _accepted_package_session()
    package.apply_package_approval_vote(session, actor="employer", decision="approve")
    assert session.package_state == "PENDING_APPROVAL"
    package.apply_package_approval_vote(session, actor="candidate", decision="approve")
    assert session.package_state == "AGREED"


def test_package_single_decline_resolves_immediately():
    session = _accepted_package_session()
    package.apply_package_approval_vote(session, actor="candidate", decision="decline")
    assert session.package_state == "DECLINED"
    assert session.employer_package_approval_vote is None


def test_package_declined_clears_package_agreed():
    session = _accepted_package_session()
    assert session.package_agreed is not None
    package.apply_package_approval_vote(session, actor="employer", decision="decline")
    assert session.package_state == "DECLINED"
    assert session.package_agreed is None


def test_package_request_more_rounds_then_both_approve():
    session = _accepted_package_session()
    package.apply_package_approval_vote(session, actor="employer", decision="request_more_rounds")
    package.apply_package_approval_vote(session, actor="candidate", decision="approve")
    assert session.package_state in ("EMPLOYER_RESPONDED", "CANDIDATE_COUNTERED")
    assert session.package_extension_count == 1
    # Employer requested more rounds -> candidate (non-requester) moves next.
    assert package.package_current_turn(session) == "candidate"

    turn = package.package_current_turn(session)
    package.apply_package_move(session, actor=turn, move="counter", package=_package(base=182_000))
    other = "candidate" if turn == "employer" else "employer"
    package.apply_package_move(session, actor=other, move="accept", package=None)
    assert session.package_state == "PENDING_APPROVAL"

    package.apply_package_approval_vote(session, actor="employer", decision="approve")
    package.apply_package_approval_vote(session, actor="candidate", decision="approve")
    assert session.package_state == "AGREED"


def test_package_extension_cap_exhausted_reaches_stalemate():
    session = _accepted_package_session()
    for _ in range(package.MAX_EXTENSIONS):
        package.apply_package_approval_vote(session, actor="employer", decision="approve")
        package.apply_package_approval_vote(session, actor="candidate", decision="request_more_rounds")
        turn = package.package_current_turn(session)
        package.apply_package_move(session, actor=turn, move="counter", package=_package(base=182_000))
        other = "candidate" if turn == "employer" else "employer"
        package.apply_package_move(session, actor=other, move="accept", package=None)

    assert session.package_extension_count == package.MAX_EXTENSIONS
    package.apply_package_approval_vote(session, actor="employer", decision="approve")
    package.apply_package_approval_vote(session, actor="candidate", decision="request_more_rounds")
    assert session.package_state == "STALEMATE"
    assert session.package_agreed is None


def test_package_already_voted_raises():
    session = _accepted_package_session()
    package.apply_package_approval_vote(session, actor="candidate", decision="approve")
    with pytest.raises(package.PackageAlreadyVoted):
        package.apply_package_approval_vote(session, actor="candidate", decision="approve")


def test_package_not_pending_approval_raises():
    session = _sealed_package_session()
    with pytest.raises(package.PackageNotPendingApproval):
        package.apply_package_approval_vote(session, actor="employer", decision="approve")


def test_package_walkaway_unaffected_by_approval_stage():
    session = _sealed_package_session()
    package.apply_package_move(session, actor="employer", move="walk", package=None)
    assert session.package_state == "WALKAWAY"


# ---------------------------------------------------------------------------
# HTTP e2e — approval endpoints, both scalar and package
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _submit_and_accept_via_http(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
        },
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]
    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 195000},
    )
    accept = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "accept", "value": None},
    )
    assert accept.json()["state"] == "PENDING_APPROVAL"
    return session_id, candidate_token, employer_token


def test_http_both_approve_then_attest(client):
    session_id, candidate_token, employer_token = _submit_and_accept_via_http(client)

    r1 = client.post(f"/api/offercheck/sessions/{session_id}/candidate/approval", json={"token": candidate_token, "decision": "approve"})
    assert r1.status_code == 200
    assert r1.json()["state"] == "PENDING_APPROVAL"
    assert r1.json()["my_approval_vote"] == "approve"
    assert r1.json()["other_approval_vote"] is None

    r2 = client.post(f"/api/offercheck/sessions/{session_id}/employer/approval", json={"token": employer_token, "decision": "approve"})
    assert r2.status_code == 200
    assert r2.json()["state"] == "AGREED"

    receipt = client.get(f"/api/offercheck/sessions/{session_id}/attest", params={"token": candidate_token})
    assert receipt.status_code == 200
    assert receipt.json()["state"] == "AGREED"


def test_http_other_side_vote_visible_once_cast(client):
    """Confirmed design: votes are shown cross-party once cast — same precedent as moves."""
    session_id, candidate_token, employer_token = _submit_and_accept_via_http(client)
    client.post(f"/api/offercheck/sessions/{session_id}/employer/approval", json={"token": employer_token, "decision": "request_more_rounds"})
    view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token}).json()
    assert view["state"] == "PENDING_APPROVAL"
    assert view["other_approval_vote"] == "request_more_rounds"
    assert view["my_approval_vote"] is None


def test_http_decline_wins_over_simultaneous_request_more_rounds(client):
    """Decline always wins the tie-break, regardless of which vote is recorded first."""
    session_id, candidate_token, employer_token = _submit_and_accept_via_http(client)
    client.post(f"/api/offercheck/sessions/{session_id}/employer/approval", json={"token": employer_token, "decision": "request_more_rounds"})
    final = client.post(f"/api/offercheck/sessions/{session_id}/candidate/approval", json={"token": candidate_token, "decision": "decline"})
    assert final.json()["state"] == "DECLINED"


def test_http_already_voted_409(client):
    session_id, candidate_token, _ = _submit_and_accept_via_http(client)
    client.post(f"/api/offercheck/sessions/{session_id}/candidate/approval", json={"token": candidate_token, "decision": "approve"})
    resp = client.post(f"/api/offercheck/sessions/{session_id}/candidate/approval", json={"token": candidate_token, "decision": "approve"})
    assert resp.status_code == 409


def test_http_approval_wrong_token_403(client):
    session_id, _, _ = _submit_and_accept_via_http(client)
    resp = client.post(f"/api/offercheck/sessions/{session_id}/candidate/approval", json={"token": "wrong-token", "decision": "approve"})
    assert resp.status_code == 403


def test_http_approval_before_pending_approval_409(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
        },
    )
    body = submit.json()
    resp = client.post(
        f"/api/offercheck/sessions/{body['session_id']}/candidate/approval",
        json={"token": body["candidate_token"], "decision": "approve"},
    )
    assert resp.status_code == 409


def test_spend_cap_raised_to_forty():
    """Confirmed design: SPEND_CAP_PER_SESSION raised from 15 to 40 to fit 3 extensions."""
    assert demo_auth.SPEND_CAP_PER_SESSION == 40
