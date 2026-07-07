"""
Tests for the Offer Check vertical (vertical/hr-offer-check branch, Phase 1).

Covers:
  - verifier.check_consistency: plausible offer passes, fabricated ones flagged
  - negotiation state machine: turn order, band-once, max 5 rounds, agree/walk
  - privacy: SessionView never leaks the other party's raw numbers
  - full HTTP e2e: demo scenario (candidate $180K vs Stripe, employer band $155K-$195K)
    goes through 3 counter rounds before converging, per acceptance criteria
"""
import pytest
from fastapi.testclient import TestClient

from app.offercheck import negotiation, store, verifier
from app.offercheck.schemas import CompetingOffer


# ---------------------------------------------------------------------------
# verifier.check_consistency
# ---------------------------------------------------------------------------

def _plausible_offer(**overrides):
    defaults = dict(
        company="Stripe",
        role="Senior Software Engineer",
        base_salary=180_000,
        equity_value=40_000,
        bonus=15_000,
        start_date="2026-09-01",
    )
    defaults.update(overrides)
    return CompetingOffer(**defaults)


def test_consistency_passes_for_plausible_offer():
    result = verifier.check_consistency(_plausible_offer(), candidate_ask=185_000)
    assert result.verified is True
    assert result.issues == []


def test_consistency_flags_implausible_bonus():
    offer = _plausible_offer(bonus=1_000_000)
    result = verifier.check_consistency(offer, candidate_ask=185_000)
    assert result.verified is False
    assert any("bonus" in issue for issue in result.issues)


def test_consistency_flags_ask_far_above_total_comp():
    offer = _plausible_offer()  # total comp = 235,000
    result = verifier.check_consistency(offer, candidate_ask=1_000_000)
    assert result.verified is False
    assert any("far above" in issue for issue in result.issues)


def test_consistency_flags_invalid_start_date():
    offer = _plausible_offer(start_date="not-a-date")
    result = verifier.check_consistency(offer, candidate_ask=185_000)
    assert result.verified is False
    assert any("start date" in issue for issue in result.issues)


def test_consistency_flags_blank_company():
    offer = _plausible_offer(company="  ")
    result = verifier.check_consistency(offer, candidate_ask=185_000)
    assert result.verified is False


# ---------------------------------------------------------------------------
# negotiation state machine (pure, in-memory)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_store():
    store.reset()
    yield
    store.reset()


def _new_session(candidate_ask=185_000.0):
    consistency = verifier.check_consistency(_plausible_offer(), candidate_ask)
    return store.create_session(_plausible_offer(), candidate_ask, consistency)


def test_initial_state_is_pending_employer():
    session = _new_session()
    assert session.state == "PENDING_EMPLOYER"
    assert negotiation.current_turn(session) == "employer"
    assert session.round_number == 0


def test_employer_cannot_move_before_setting_band():
    session = _new_session()
    with pytest.raises(negotiation.BandNotSet):
        negotiation.apply_move(session, actor="employer", move="accept", value=None)


def test_band_can_only_be_set_once():
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    with pytest.raises(negotiation.BandAlreadySet):
        negotiation.set_employer_band(session, 155_000, 175_000, 195_000)


def test_candidate_cannot_move_out_of_turn():
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    with pytest.raises(negotiation.WrongTurn):
        negotiation.apply_move(session, actor="candidate", move="accept", value=None)


def test_employer_accept_agrees_at_candidate_ask():
    session = _new_session(candidate_ask=185_000.0)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)
    assert session.state == "AGREED"
    assert session.agreed_price == 185_000.0


def test_full_revision_loop_converges_after_three_rounds():
    """Demo scenario: candidate $180K vs Stripe offer, employer band $155K-$195K."""
    session = _new_session(candidate_ask=185_000.0)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)

    negotiation.apply_move(session, actor="employer", move="counter", value=170_000.0)
    assert session.state == "EMPLOYER_RESPONDED"
    assert negotiation.current_turn(session) == "candidate"

    negotiation.apply_move(session, actor="candidate", move="counter", value=180_000.0)
    assert session.state == "CANDIDATE_COUNTERED"
    assert negotiation.current_turn(session) == "employer"

    negotiation.apply_move(session, actor="employer", move="counter", value=177_000.0)
    assert session.state == "EMPLOYER_RESPONDED"

    negotiation.apply_move(session, actor="candidate", move="accept", value=None)
    assert session.state == "AGREED"
    assert session.agreed_price == 177_000.0
    assert session.round_number == 4
    assert len([r for r in session.history if r.move == "counter"]) >= 3


def test_walkaway_terminates_session():
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="walk", value=None)
    assert session.state == "WALKAWAY"
    with pytest.raises(negotiation.SessionTerminal):
        negotiation.apply_move(session, actor="candidate", move="accept", value=None)


def test_max_five_rounds_then_auto_expire():
    session = _new_session(candidate_ask=200_000.0)
    negotiation.set_employer_band(session, 100_000, 110_000, 120_000)

    negotiation.apply_move(session, actor="employer", move="counter", value=110_000.0)
    negotiation.apply_move(session, actor="candidate", move="counter", value=195_000.0)
    negotiation.apply_move(session, actor="employer", move="counter", value=112_000.0)
    negotiation.apply_move(session, actor="candidate", move="counter", value=190_000.0)
    negotiation.apply_move(session, actor="employer", move="counter", value=114_000.0)

    assert session.round_number == 5
    assert session.state == "EXPIRED"
    with pytest.raises(negotiation.SessionTerminal):
        negotiation.apply_move(session, actor="candidate", move="accept", value=None)


def test_counter_requires_positive_value():
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    with pytest.raises(negotiation.InvalidMove):
        negotiation.apply_move(session, actor="employer", move="counter", value=None)
    with pytest.raises(negotiation.InvalidMove):
        negotiation.apply_move(session, actor="employer", move="counter", value=-5)


# ---------------------------------------------------------------------------
# HTTP e2e — privacy + full flow
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_e2e_demo_scenario_full_revision_loop(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {
                "company": "Stripe",
                "role": "Senior Software Engineer",
                "base_salary": 165_000,
                "equity_value": 40_000,
                "bonus": 15_000,
                "start_date": "2026-09-01",
            },
            "candidate_ask": 185_000,
        },
    )
    assert submit.status_code == 200
    body = submit.json()
    session_id = body["session_id"]
    candidate_token = body["candidate_token"]
    employer_token = body["employer_token"]
    assert body["consistency"]["verified"] is True

    # Employer view before band is set: no raw candidate numbers anywhere.
    pre_band_view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": employer_token})
    assert pre_band_view.status_code == 200
    assert "185000" not in pre_band_view.text
    assert pre_band_view.json()["gap_pct"] is None

    band = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155_000, "band_mid": 175_000, "band_max": 195_000},
    )
    assert band.status_code == 200
    assert band.json()["gap_pct"] == pytest.approx((185_000 - 175_000) / 175_000 * 100)

    # Employer band can only be submitted once.
    dup = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155_000, "band_mid": 175_000, "band_max": 195_000},
    )
    assert dup.status_code == 409

    r1 = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "counter", "value": 170_000},
    )
    assert r1.status_code == 200
    assert "170000" not in client.get(
        f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token}
    ).text

    r2 = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/move",
        json={"token": candidate_token, "move": "counter", "value": 180_000},
    )
    assert r2.status_code == 200

    r3 = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "counter", "value": 177_000},
    )
    assert r3.status_code == 200

    final = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/move",
        json={"token": candidate_token, "move": "accept", "value": None},
    )
    assert final.status_code == 200
    final_body = final.json()
    assert final_body["state"] == "AGREED"
    assert final_body["agreed_price"] == 177_000
    assert final_body["round_number"] == 4
    assert len([h for h in final_body["history"] if h["move"] == "counter"]) == 3

    # Neither view ever exposed the employer's raw band or the candidate's raw offer letter.
    candidate_view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token})
    assert "band_min" not in candidate_view.text
    assert "155000" not in candidate_view.text

    employer_view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": employer_token})
    assert "Stripe" not in employer_view.text
    assert "165000" not in employer_view.text


def test_invalid_token_rejected(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {
                "company": "Google",
                "role": "Staff Engineer",
                "base_salary": 200_000,
                "equity_value": 80_000,
                "bonus": 20_000,
                "start_date": "2026-10-01",
            },
            "candidate_ask": 220_000,
        },
    )
    session_id = submit.json()["session_id"]

    resp = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": "not-a-real-token"})
    assert resp.status_code == 403


def test_unknown_session_returns_404(client):
    resp = client.get("/api/offercheck/sessions/does-not-exist", params={"token": "x"})
    assert resp.status_code == 404
