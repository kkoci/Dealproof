"""
Tests for the Offer Check vertical (vertical/hr-offer-check branch, Phase 1 + 2).

Covers:
  - verifier.check_consistency: plausible offer passes, fabricated ones flagged
  - negotiation state machine: turn order, band-once, max 5 rounds, agree/walk
  - privacy: SessionView never leaks the other party's raw numbers
  - full HTTP e2e: demo scenario (candidate $180K vs Stripe, employer band $155K-$195K)
    goes through 3 counter rounds before converging, per acceptance criteria
  - Phase 2: TDX attestation on session close, DCAP quote parsing, PDF offer-letter parsing
"""
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.offercheck import invites, negotiation, parsing, rate_limit, store, verifier
from app.offercheck.integrations import market_data
from app.offercheck.integrations.market_data import MarketRange
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
    """Message is self-contained — spells out both real values, since they never otherwise
    appear together on the results screen (see verifier.check_consistency)."""
    offer = _plausible_offer()  # total comp = 235,000
    result = verifier.check_consistency(offer, candidate_ask=1_000_000)
    assert result.verified is False
    assert any("$1,000,000" in issue and "$235,000" in issue for issue in result.issues)


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
    rate_limit.reset()
    invites.reset()
    market_data.reset_cache()
    yield
    store.reset()
    rate_limit.reset()
    invites.reset()
    market_data.reset_cache()


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
    """An accept lands on PENDING_APPROVAL, not AGREED directly — see
    negotiation.apply_approval_vote(). Both sides must separately approve."""
    session = _new_session(candidate_ask=185_000.0)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)
    assert session.state == "PENDING_APPROVAL"
    assert session.agreed_price == 185_000.0

    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    assert session.state == "PENDING_APPROVAL"  # only one side has voted so far
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
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
    assert session.state == "PENDING_APPROVAL"
    assert session.agreed_price == 177_000.0
    assert session.round_number == 4
    assert len([r for r in session.history if r.move == "counter"]) >= 3

    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    assert session.state == "AGREED"
    assert session.agreed_price == 177_000.0


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

    accept = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/move",
        json={"token": candidate_token, "move": "accept", "value": None},
    )
    assert accept.status_code == 200
    accept_body = accept.json()
    assert accept_body["state"] == "PENDING_APPROVAL"
    assert accept_body["agreed_price"] == 177_000
    assert accept_body["round_number"] == 4
    assert len([h for h in accept_body["history"] if h["move"] == "counter"]) == 3

    # Both sides must separately approve before the session is genuinely terminal.
    cand_approve = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/approval",
        json={"token": candidate_token, "decision": "approve"},
    )
    assert cand_approve.status_code == 200
    assert cand_approve.json()["state"] == "PENDING_APPROVAL"  # only one side has voted so far

    final = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/approval",
        json={"token": employer_token, "decision": "approve"},
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


# ---------------------------------------------------------------------------
# Phase 2: attestation
# ---------------------------------------------------------------------------

def test_attested_terms_excludes_private_inputs():
    """agreed_price is the disclosed outcome and belongs in the attestation —
    but the private inputs that produced it (band, offer letter) must not."""
    session = _new_session(candidate_ask=185_000.0)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")

    terms = negotiation.attested_terms(session)
    serialized = str(terms)
    assert "155000" not in serialized  # band_min, private and never disclosed
    assert "175000" not in serialized  # band_mid, private and never disclosed
    assert "Stripe" not in serialized
    assert terms["state"] == "AGREED"
    assert terms["agreed_price"] == 185_000.0  # the disclosed outcome — expected to be present
    assert terms["competing_offer_hash"] == negotiation.competing_offer_hash(session)
    assert terms["employer_band_hash"] == negotiation.employer_band_hash(session)


def test_opening_employer_offer_set_once_on_first_counter():
    """opening_employer_offer snapshots the employer's FIRST counter and never
    changes on later employer counters — the external anchor final_gap_pct is
    measured against."""
    session = _new_session(candidate_ask=185_000.0)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    assert session.opening_employer_offer is None

    negotiation.apply_move(session, actor="employer", move="counter", value=170_000.0)
    assert session.opening_employer_offer == 170_000.0

    negotiation.apply_move(session, actor="candidate", move="counter", value=180_000.0)
    negotiation.apply_move(session, actor="employer", move="counter", value=177_000.0)
    assert session.opening_employer_offer == 170_000.0  # unchanged by the second employer counter
    assert session.employer_current_offer == 177_000.0


def test_final_gap_pct_correct_for_agreed_session():
    session = _new_session(candidate_ask=185_000.0)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="counter", value=170_000.0)
    negotiation.apply_move(session, actor="candidate", move="counter", value=180_000.0)
    negotiation.apply_move(session, actor="employer", move="counter", value=177_000.0)
    negotiation.apply_move(session, actor="candidate", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")

    assert session.state == "AGREED"
    assert session.agreed_price == 177_000.0
    assert session.opening_employer_offer == 170_000.0
    expected = (177_000.0 - 170_000.0) / 170_000.0 * 100
    assert negotiation.final_gap_pct(session) == pytest.approx(expected)


def test_final_gap_pct_none_when_session_never_agrees():
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="counter", value=170_000.0)
    negotiation.apply_move(session, actor="candidate", move="counter", value=180_000.0)
    negotiation.apply_move(session, actor="employer", move="walk", value=None)

    assert session.state == "WALKAWAY"
    assert session.agreed_price is None
    assert session.opening_employer_offer == 170_000.0  # was set before the walk
    assert negotiation.final_gap_pct(session) is None


def test_final_gap_pct_none_when_employer_never_countered():
    """Employer's first move is an immediate accept — opening_employer_offer
    stays None even though the session goes on to reach AGREED."""
    session = _new_session(candidate_ask=185_000.0)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")

    assert session.state == "AGREED"
    assert session.agreed_price == 185_000.0
    assert session.opening_employer_offer is None
    assert negotiation.final_gap_pct(session) is None


def test_final_gap_pct_included_in_attested_terms():
    session = _new_session(candidate_ask=185_000.0)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="counter", value=170_000.0)
    negotiation.apply_move(session, actor="candidate", move="counter", value=180_000.0)
    negotiation.apply_move(session, actor="employer", move="counter", value=177_000.0)
    negotiation.apply_move(session, actor="candidate", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")

    terms = negotiation.attested_terms(session)
    expected = negotiation.final_gap_pct(session)
    assert terms["final_gap_pct"] == pytest.approx(expected)
    # the raw opening offer stays private, same discipline as band_min/band_mid above —
    # only the derived percentage is attested, never the number it was computed from
    assert "170000" not in str({k: v for k, v in terms.items() if k != "final_gap_pct"})


# ---------------------------------------------------------------------------
# market comparator — negotiation.market_percentile (pure) + attested_terms
# ---------------------------------------------------------------------------

def _agreed_session(agreed_price=185_000.0):
    """A session sitting at AGREED, with a known agreed_price, for market_percentile tests."""
    session = _new_session(candidate_ask=agreed_price)
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    assert session.state == "AGREED"
    assert session.agreed_price == agreed_price
    return session


def test_market_percentile_correct_value_within_range():
    session = _agreed_session(agreed_price=185_000.0)
    market_range = MarketRange(p25=150_000.0, p50=180_000.0, p75=210_000.0)
    # 185,000 is between p50 and p75: 50 + 25 * (185000-180000)/(210000-180000) = 54.166...
    expected = 50.0 + 25.0 * (185_000.0 - 180_000.0) / (210_000.0 - 180_000.0)
    assert negotiation.market_percentile(session, market_range) == pytest.approx(expected)


def test_market_percentile_clamped_outside_fetched_range():
    session = _agreed_session(agreed_price=500_000.0)  # way above p75
    market_range = MarketRange(p25=150_000.0, p50=180_000.0, p75=210_000.0)
    assert negotiation.market_percentile(session, market_range) == 100.0

    session_low = _agreed_session(agreed_price=10_000.0)  # way below p25
    assert negotiation.market_percentile(session_low, market_range) == 0.0


def test_market_percentile_none_when_market_range_is_none():
    session = _agreed_session()
    assert negotiation.market_percentile(session, None) is None


def test_market_percentile_none_when_session_never_agreed():
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="walk", value=None)
    assert session.state == "WALKAWAY"
    assert session.agreed_price is None

    market_range = MarketRange(p25=150_000.0, p50=180_000.0, p75=210_000.0)
    assert negotiation.market_percentile(session, market_range) is None


def test_market_percentile_included_in_attested_terms_and_raw_range_excluded():
    session = _agreed_session(agreed_price=185_000.0)
    market_range = MarketRange(p25=150_000.0, p50=180_000.0, p75=210_000.0)
    session.market_percentile = negotiation.market_percentile(session, market_range)

    terms = negotiation.attested_terms(session)
    assert terms["market_percentile"] == pytest.approx(session.market_percentile)
    # the raw fetched range never lands in the attested payload — only the derived
    # percentile does, same discipline as opening_employer_offer vs. final_gap_pct
    serialized = str({k: v for k, v in terms.items() if k != "market_percentile"})
    assert "150000" not in serialized
    assert "210000" not in serialized


def test_market_percentile_none_in_attested_terms_when_never_computed():
    """A terminal session that never reached AGREED (so _maybe_attest never fetches
    market data) attests market_percentile: None, same as final_gap_pct."""
    session = _new_session()
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    negotiation.apply_move(session, actor="employer", move="walk", value=None)
    terms = negotiation.attested_terms(session)
    assert terms["market_percentile"] is None


# ---------------------------------------------------------------------------
# market comparator — integrations.market_data.fetch_market_range (external HTTP)
# ---------------------------------------------------------------------------

def _mock_market_httpx_client(json_response: dict | None = None, raises: Exception | None = None):
    mock_response = MagicMock()
    if raises is not None:
        mock_response.raise_for_status = MagicMock(side_effect=raises)
    else:
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = json_response

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_fetch_market_range_returns_none_when_not_configured():
    with patch("app.offercheck.integrations.market_data.settings.market_data_api_key", ""):
        result = await market_data.fetch_market_range("Senior Software Engineer", None, "United States")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_market_range_returns_range_when_configured():
    mock_ctx = _mock_market_httpx_client({"percentile_25": 150_000, "percentile_50": 180_000, "percentile_75": 210_000})
    with patch("app.offercheck.integrations.market_data.settings.market_data_api_key", "pk_test_fake"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        result = await market_data.fetch_market_range("Senior Software Engineer", None, "United States")
    assert result == MarketRange(p25=150_000.0, p50=180_000.0, p75=210_000.0)


@pytest.mark.asyncio
async def test_fetch_market_range_returns_none_on_http_error_without_raising():
    """A failed/errored external fetch never raises — it degrades to None."""
    mock_ctx = _mock_market_httpx_client(raises=Exception("boom"))
    with patch("app.offercheck.integrations.market_data.settings.market_data_api_key", "pk_test_fake"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        result = await market_data.fetch_market_range("Senior Software Engineer", None, "United States")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_market_range_returns_none_on_malformed_response():
    mock_ctx = _mock_market_httpx_client({"unexpected": "shape"})
    with patch("app.offercheck.integrations.market_data.settings.market_data_api_key", "pk_test_fake"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        result = await market_data.fetch_market_range("Senior Software Engineer", None, "United States")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_market_range_caches_result_and_does_not_refetch():
    mock_ctx = _mock_market_httpx_client({"percentile_25": 150_000, "percentile_50": 180_000, "percentile_75": 210_000})
    with patch("app.offercheck.integrations.market_data.settings.market_data_api_key", "pk_test_fake"), \
         patch("httpx.AsyncClient", return_value=mock_ctx) as mock_cls:
        first = await market_data.fetch_market_range("Senior Software Engineer", None, "United States")
        second = await market_data.fetch_market_range("Senior Software Engineer", None, "United States")
    assert first == second
    mock_cls.assert_called_once()  # only one real HTTP client constructed — second call hit the cache


@pytest.mark.asyncio
async def test_fetch_market_range_cache_is_case_and_whitespace_insensitive():
    mock_ctx = _mock_market_httpx_client({"percentile_25": 150_000, "percentile_50": 180_000, "percentile_75": 210_000})
    with patch("app.offercheck.integrations.market_data.settings.market_data_api_key", "pk_test_fake"), \
         patch("httpx.AsyncClient", return_value=mock_ctx) as mock_cls:
        await market_data.fetch_market_range("Senior Software Engineer", None, "United States")
        await market_data.fetch_market_range("  senior software engineer  ", None, "united states")
    mock_cls.assert_called_once()


# ---------------------------------------------------------------------------
# market comparator — HTTP e2e wiring (routes.py::_maybe_attest)
# ---------------------------------------------------------------------------

def test_e2e_agreed_session_persists_market_percentile_from_configured_source(client):
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

    mock_ctx = _mock_market_httpx_client({"percentile_25": 150_000, "percentile_50": 180_000, "percentile_75": 210_000})
    with patch("app.offercheck.integrations.market_data.settings.market_data_api_key", "pk_test_fake"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        accept = client.post(
            f"/api/offercheck/sessions/{session_id}/employer/move",
            json={"token": employer_token, "move": "accept"},
        )
        assert accept.status_code == 200
        client.post(
            f"/api/offercheck/sessions/{session_id}/employer/approval",
            json={"token": employer_token, "decision": "approve"},
        )
        approve = client.post(
            f"/api/offercheck/sessions/{session_id}/candidate/approval",
            json={"token": candidate_token, "decision": "approve"},
        )

    assert approve.status_code == 200
    view = approve.json()
    assert view["state"] == "AGREED"
    expected = 50.0 + 25.0 * (185_000.0 - 180_000.0) / (210_000.0 - 180_000.0)
    assert view["market_percentile"] == pytest.approx(expected)

    receipt = client.get(f"/api/offercheck/sessions/{session_id}/attest", params={"token": candidate_token})
    assert receipt.status_code == 200
    assert receipt.json()["market_percentile"] == pytest.approx(expected)


def test_e2e_agreed_session_market_percentile_none_when_source_unconfigured(client):
    """The core promise: an unconfigured/unavailable market data source never blocks
    the session from reaching AGREED — it just leaves market_percentile null."""
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

    with patch("app.offercheck.integrations.market_data.settings.market_data_api_key", ""):
        accept = client.post(
            f"/api/offercheck/sessions/{session_id}/employer/move",
            json={"token": employer_token, "move": "accept"},
        )
        client.post(
            f"/api/offercheck/sessions/{session_id}/employer/approval",
            json={"token": employer_token, "decision": "approve"},
        )
        approve = client.post(
            f"/api/offercheck/sessions/{session_id}/candidate/approval",
            json={"token": candidate_token, "decision": "approve"},
        )

    assert accept.status_code == 200
    assert approve.status_code == 200
    view = approve.json()
    assert view["state"] == "AGREED"  # never blocked by the missing market data source
    assert view["agreed_price"] == 185_000.0
    assert view["market_percentile"] is None


def test_competing_offer_hash_deterministic_and_sensitive():
    session_a = _new_session(candidate_ask=185_000.0)
    session_b = _new_session(candidate_ask=185_000.0)
    assert negotiation.competing_offer_hash(session_a) == negotiation.competing_offer_hash(session_b)

    session_c = _new_session(candidate_ask=185_000.0)
    session_c.competing_offer.base_salary = 999_000
    assert negotiation.competing_offer_hash(session_c) != negotiation.competing_offer_hash(session_a)


def test_employer_band_hash_none_before_band_set():
    session = _new_session()
    assert negotiation.employer_band_hash(session) is None
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    assert negotiation.employer_band_hash(session) is not None


def test_attest_endpoint_unavailable_before_terminal(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {
                "company": "Meta", "role": "Engineer", "base_salary": 190_000,
                "equity_value": 50_000, "bonus": 10_000, "start_date": "2026-08-01",
            },
            "candidate_ask": 200_000,
        },
    )
    body = submit.json()
    resp = client.get(
        f"/api/offercheck/sessions/{body['session_id']}/attest",
        params={"token": body["candidate_token"]},
    )
    assert resp.status_code == 409


def test_attest_and_dcap_verify_after_agreement(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {
                "company": "Meta", "role": "Engineer", "base_salary": 190_000,
                "equity_value": 50_000, "bonus": 10_000, "start_date": "2026-08-01",
            },
            "candidate_ask": 200_000,
        },
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 180_000, "band_mid": 195_000, "band_max": 210_000},
    )
    move = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "accept", "value": None},
    )
    assert move.json()["state"] == "PENDING_APPROVAL"

    # Both sides must approve before the session is terminal and attestation fires.
    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/approval",
        json={"token": employer_token, "decision": "approve"},
    )
    approve = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/approval",
        json={"token": candidate_token, "decision": "approve"},
    )
    assert approve.json()["state"] == "AGREED"

    receipt = client.get(f"/api/offercheck/sessions/{session_id}/attest", params={"token": candidate_token})
    assert receipt.status_code == 200
    receipt_body = receipt.json()
    assert receipt_body["state"] == "AGREED"
    assert receipt_body["agreed_price"] == 200_000
    assert receipt_body["attestation"].startswith("sim_quote:")
    assert receipt_body["tee_attested"] is False  # simulation mode in tests
    assert receipt_body["tee_mode"] == "simulation"
    assert "Meta" not in receipt.text
    assert "190000" not in receipt.text

    # Employer's token works too — the outcome is mutually known once terminal.
    receipt_as_employer = client.get(f"/api/offercheck/sessions/{session_id}/attest", params={"token": employer_token})
    assert receipt_as_employer.status_code == 200
    assert receipt_as_employer.json()["attestation"] == receipt_body["attestation"]

    dcap = client.get(f"/api/offercheck/sessions/{session_id}/dcap-verify", params={"token": candidate_token})
    assert dcap.status_code == 200
    dcap_body = dcap.json()
    assert dcap_body["mode"] == "simulation"
    assert dcap_body["verification_status"] == "simulation_only"
    assert dcap_body["session_id"] == session_id


def test_attest_and_dcap_available_after_walkaway(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {
                "company": "Netflix", "role": "Engineer", "base_salary": 210_000,
                "equity_value": 60_000, "bonus": 10_000, "start_date": "2026-08-01",
            },
            "candidate_ask": 230_000,
        },
    )
    body = submit.json()
    session_id, employer_token = body["session_id"], body["employer_token"]

    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 150_000, "band_mid": 160_000, "band_max": 170_000},
    )
    walk = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "walk", "value": None},
    )
    assert walk.json()["state"] == "WALKAWAY"

    receipt = client.get(f"/api/offercheck/sessions/{session_id}/attest", params={"token": employer_token})
    assert receipt.status_code == 200
    assert receipt.json()["state"] == "WALKAWAY"
    assert receipt.json()["agreed_price"] is None


# ---------------------------------------------------------------------------
# Phase 2: PDF offer-letter parsing
# ---------------------------------------------------------------------------

def _mock_pdf_reader(text: str):
    reader = MagicMock()
    page = MagicMock()
    page.extract_text.return_value = text
    reader.pages = [page]
    return reader


def _mock_anthropic_response(payload: dict):
    import json as _json
    msg = MagicMock()
    msg.content = [MagicMock(text=_json.dumps(payload))]
    return msg


def test_extract_text_from_pdf_raises_on_empty_text():
    with patch("app.offercheck.parsing.PdfReader", return_value=_mock_pdf_reader("")):
        with pytest.raises(parsing.OfferLetterParseError):
            parsing.extract_text_from_pdf(b"%PDF-fake")


def test_extract_text_from_pdf_raises_on_unreadable_bytes():
    with patch("app.offercheck.parsing.PdfReader", side_effect=Exception("not a pdf")):
        with pytest.raises(parsing.OfferLetterParseError):
            parsing.extract_text_from_pdf(b"not-a-real-pdf")


@pytest.mark.asyncio
async def test_extract_offer_from_text_parses_claude_json():
    expected = {
        "company": "Stripe", "role": "Senior Engineer", "base_salary": 165000,
        "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01",
        "confidence": "high", "notes": [],
    }
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response(expected))
    with patch("app.offercheck.parsing.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await parsing.extract_offer_from_text("some offer letter text")
    assert result == expected


@pytest.mark.asyncio
async def test_extract_offer_from_text_raises_on_claude_failure():
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=RuntimeError("api down"))
    with patch("app.offercheck.parsing.anthropic.AsyncAnthropic", return_value=mock_client):
        with pytest.raises(parsing.OfferLetterParseError):
            await parsing.extract_offer_from_text("some offer letter text")


def test_parse_offer_letter_endpoint_returns_draft_fields(client):
    extracted = {
        "company": "Stripe", "role": "Senior Engineer", "base_salary": 165000,
        "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01",
        "confidence": "high", "notes": ["inferred equity from grant/vesting"],
    }
    with patch("app.offercheck.parsing.extract_text_from_pdf", return_value="raw pdf text"), \
         patch("app.offercheck.parsing.anthropic.AsyncAnthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=_mock_anthropic_response(extracted))
        mock_anthropic_cls.return_value = mock_client

        resp = client.post(
            "/api/offercheck/parse-offer-letter",
            files={"file": ("offer.pdf", io.BytesIO(b"%PDF-fake-bytes"), "application/pdf")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["competing_offer"]["company"] == "Stripe"
    assert body["confidence"] == "high"
    assert body["notes"] == ["inferred equity from grant/vesting"]


def test_parse_offer_letter_endpoint_422_on_unreadable_pdf(client):
    with patch("app.offercheck.parsing.PdfReader", side_effect=Exception("not a pdf")):
        resp = client.post(
            "/api/offercheck/parse-offer-letter",
            files={"file": ("offer.pdf", io.BytesIO(b"garbage"), "application/pdf")},
        )
    assert resp.status_code == 422
