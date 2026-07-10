"""
Tests for Offer Check Phase 2A — agentic negotiation (offercheck_phase2_spec.md).

Covers:
  - CandidateAgent / EmployerAgent: hard floor/band clamp enforced in code,
    unexpected action values normalised, own-vs-opposing message role mapping
  - mediator.build_agents / run_agentic_negotiation: AgenticNotReady before
    both sides seal, full negotiation converges to AGREED via the real state
    machine, reasoning never crosses into the opposing agent's prompt
  - HTTP e2e: seal at submit/band time, agentic_ready flag, start-agentic
    end to end (mocked Claude), 412 before sealing, invalid token rejected

Mocking note: patching `anthropic.AsyncAnthropic` by module path doesn't
give CandidateAgent and EmployerAgent independently different mocks — both
modules share the same `anthropic` module object, so the two patches collide
on the same attribute. Instead, construct real agent instances (no network
call happens at construction time) and patch `agent.client.messages.create`
directly — the same pattern tests/test_negotiation.py uses for
BuyerAgent/SellerAgent.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.offercheck import negotiation, rate_limit, store, verifier
from app.offercheck.agents import mediator
from app.offercheck.agents.candidate_agent import CandidateAgent
from app.offercheck.agents.employer_agent import EmployerAgent
from app.offercheck.schemas import CompetingOffer


@pytest.fixture(autouse=True)
def _clear_store():
    store.reset()
    rate_limit.reset()
    yield
    store.reset()
    rate_limit.reset()


def _plausible_offer(**overrides):
    defaults = dict(
        company="Stripe", role="Senior Software Engineer", base_salary=180_000,
        equity_value=40_000, bonus=15_000, start_date="2026-09-01",
    )
    defaults.update(overrides)
    return CompetingOffer(**defaults)


def _mock_response(payload: dict):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    return msg


def _scripted(responses: list[dict]):
    """Async side_effect that returns each payload in order, then repeats the last."""
    calls = {"n": 0}

    async def _side_effect(*args, **kwargs):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return _mock_response(responses[i])

    return _side_effect


# ---------------------------------------------------------------------------
# CandidateAgent / EmployerAgent — hard clamps + response normalisation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_candidate_agent_clamps_value_to_floor():
    agent = CandidateAgent(opening_ask=200_000, floor=150_000)
    with patch.object(agent.client.messages, "create", side_effect=_scripted([{"action": "counter", "value": 100_000, "reasoning": "x"}])):
        result = await agent.decide(employer_offer=140_000, history=[])
    assert result["value"] == 150_000  # clamped up to floor despite Claude suggesting less


@pytest.mark.asyncio
async def test_candidate_agent_normalises_unexpected_action():
    agent = CandidateAgent(opening_ask=200_000, floor=150_000)
    with patch.object(agent.client.messages, "create", side_effect=_scripted([{"action": "reject", "value": 180_000}])):
        result = await agent.decide(employer_offer=140_000, history=[])
    assert result["action"] == "counter"


@pytest.mark.asyncio
async def test_employer_agent_clamps_value_to_band():
    agent = EmployerAgent(band_min=150_000, band_mid=175_000, band_max=195_000)
    with patch.object(agent.client.messages, "create", side_effect=_scripted([{"action": "counter", "value": 500_000, "reasoning": "x"}])):
        result = await agent.decide(candidate_ask=210_000, history=[])
    assert result["value"] == 195_000  # clamped down to band max despite Claude suggesting more


def test_agent_message_role_mapping():
    agent = CandidateAgent(opening_ask=200_000, floor=150_000)
    history = [
        {"role": "candidate", "content": {"action": "counter", "value": 190_000, "reasoning": "my own reasoning"}},
        {"role": "employer", "content": {"action": "counter", "value": 170_000}},
    ]
    messages = agent._build_messages(history, employer_offer=170_000)
    assert messages[0]["role"] == "assistant"  # candidate's own past turn
    assert messages[1]["role"] == "user"       # employer's turn, from candidate's POV
    assert messages[2]["role"] == "user"       # current offer prompt


# ---------------------------------------------------------------------------
# mediator.build_agents / run_agentic_negotiation
# ---------------------------------------------------------------------------

def _sealed_session(candidate_ask=190_000.0, candidate_floor=175_000.0, band=(155_000.0, 175_000.0, 195_000.0), authority_limit=195_000.0):
    consistency = verifier.check_consistency(_plausible_offer(), candidate_ask)
    session = store.create_session(_plausible_offer(), candidate_ask, consistency, candidate_floor=candidate_floor)
    negotiation.set_employer_band(session, *band)
    session.employer_authority_limit = authority_limit
    return session


def test_build_agents_not_ready_without_candidate_floor():
    consistency = verifier.check_consistency(_plausible_offer(), 190_000.0)
    session = store.create_session(_plausible_offer(), 190_000.0, consistency)  # no candidate_floor
    negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    session.employer_authority_limit = 195_000.0
    with pytest.raises(mediator.AgenticNotReady):
        mediator.build_agents(session)


def test_build_agents_not_ready_without_employer_authority_limit():
    session = _sealed_session()
    session.employer_authority_limit = None
    with pytest.raises(mediator.AgenticNotReady):
        mediator.build_agents(session)


@pytest.mark.asyncio
async def test_agentic_negotiation_converges_to_agreed():
    session = _sealed_session(candidate_ask=190_000.0, candidate_floor=175_000.0)
    candidate_agent, employer_agent = mediator.build_agents(session)

    emp_effect = _scripted([
        {"action": "counter", "value": 170_000, "reasoning": "opening low"},
        {"action": "counter", "value": 177_000, "reasoning": "meeting closer"},
    ])
    cand_effect = _scripted([
        {"action": "counter", "value": 185_000, "reasoning": "still want more"},
        {"action": "accept", "value": 177_000, "reasoning": "good enough"},
    ])

    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect):
        transcript = await mediator.run_agentic_negotiation(session, candidate_agent, employer_agent)

    assert session.state == "AGREED"
    assert session.agreed_price == 177_000.0
    assert session.agentic_mode is True
    assert len(transcript) == 4
    assert transcript[0] == {"round": 1, "actor": "employer", "move": "counter", "value": 170_000.0}
    assert transcript[3]["move"] == "accept"
    assert all("reasoning" not in r for r in transcript)  # no reasoning anywhere in the returned transcript


@pytest.mark.asyncio
async def test_agentic_reasoning_never_crosses_the_boundary():
    session = _sealed_session(candidate_ask=190_000.0, candidate_floor=175_000.0)
    candidate_agent, employer_agent = mediator.build_agents(session)

    emp_effect = _scripted([
        {"action": "counter", "value": 170_000, "reasoning": "EMPLOYER_SECRET_REASONING"},
        {"action": "accept", "value": 185_000, "reasoning": "closing the deal"},
    ])
    cand_effect = _scripted([
        {"action": "counter", "value": 185_000, "reasoning": "CANDIDATE_SECRET_REASONING"},
    ])

    emp_create = AsyncMock(side_effect=emp_effect)
    cand_create = AsyncMock(side_effect=cand_effect)
    with patch.object(employer_agent.client.messages, "create", emp_create), \
         patch.object(candidate_agent.client.messages, "create", cand_create):
        await mediator.run_agentic_negotiation(session, candidate_agent, employer_agent)

    # Employer's 2nd call must not contain the candidate's reasoning, but must retain its own.
    emp_second_call = emp_create.call_args_list[1].kwargs
    emp_messages_json = json.dumps(emp_second_call["messages"])
    assert "CANDIDATE_SECRET_REASONING" not in emp_messages_json
    assert "EMPLOYER_SECRET_REASONING" in emp_messages_json

    # Candidate's only call must not contain the employer's reasoning either.
    cand_first_call = cand_create.call_args_list[0].kwargs
    cand_messages_json = json.dumps(cand_first_call["messages"])
    assert "EMPLOYER_SECRET_REASONING" not in cand_messages_json


@pytest.mark.asyncio
async def test_agentic_negotiation_can_reach_walkaway_within_max_rounds():
    session = _sealed_session(candidate_ask=250_000.0, candidate_floor=240_000.0, band=(100_000.0, 110_000.0, 120_000.0), authority_limit=120_000.0)
    candidate_agent, employer_agent = mediator.build_agents(session)

    emp_effect = _scripted([{"action": "walk", "value": None, "reasoning": "too far apart"}])
    cand_effect = _scripted([{"action": "counter", "value": 245_000, "reasoning": "x"}])

    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect):
        transcript = await mediator.run_agentic_negotiation(session, candidate_agent, employer_agent)

    assert session.state == "WALKAWAY"
    assert transcript[-1]["move"] == "walk"
    assert session.round_number <= session.max_rounds


# ---------------------------------------------------------------------------
# HTTP e2e
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_agentic_ready_flag_flips_true_once_both_sides_sealed(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
            "candidate_floor": 175000,
            "candidate_priorities": "base matters more than equity",
        },
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    pre = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token})
    assert pre.json()["agentic_ready"] is False

    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={
            "employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 195000,
            "employer_authority_limit": 195000, "employer_priorities": "equity is more flexible than base",
        },
    )

    post = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token})
    assert post.json()["agentic_ready"] is True

    # Sealed values themselves must never appear anywhere in the response.
    assert "175000" not in pre.text
    assert "175000" not in post.text
    assert "candidate_floor" not in post.text
    assert "employer_authority_limit" not in post.text


def test_start_agentic_412_before_sealed(client):
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
        f"/api/offercheck/sessions/{body['session_id']}/start-agentic",
        json={"token": body["candidate_token"]},
    )
    assert resp.status_code == 412


def test_start_agentic_invalid_token_rejected(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
            "candidate_floor": 175000,
        },
    )
    session_id = submit.json()["session_id"]
    resp = client.post(
        f"/api/offercheck/sessions/{session_id}/start-agentic",
        json={"token": "not-a-real-token"},
    )
    # Neither a valid party token nor a demo token was supplied — unauthenticated.
    assert resp.status_code == 401


def test_start_agentic_end_to_end(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
            "candidate_floor": 175000,
        },
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 195000,
              "employer_authority_limit": 195000},
    )

    from app.offercheck import store as offercheck_store
    session = offercheck_store.get_session(session_id)
    from app.offercheck.agents import mediator as mediator_module
    candidate_agent, employer_agent = mediator_module.build_agents(session)

    emp_effect = _scripted([{"action": "accept", "value": 190000, "reasoning": "fine"}])
    cand_effect = _scripted([{"action": "counter", "value": 190000, "reasoning": "x"}])

    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect), \
         patch("app.offercheck.agents.mediator.build_agents", return_value=(candidate_agent, employer_agent)):
        resp = client.post(f"/api/offercheck/sessions/{session_id}/start-agentic", json={"token": candidate_token})

    assert resp.status_code == 200
    result = resp.json()
    assert result["state"] == "AGREED"
    assert result["agreed_price"] == 190000
    assert len(result["transcript"]) == 1
    assert result["attestation"].startswith("sim_quote:")
    assert result["credential"]["genuine_negotiation"] is True
    assert "155000" not in resp.text  # employer band never leaks
    assert "reasoning" not in resp.text  # never leaks to the API response either


def test_round_summary_value_hidden_for_human_moves_exposed_after_agentic(client):
    """RoundSummary.value must stay None for human-driven rounds (non-negotiable gap%-only
    privacy invariant) and only appear once session.agentic_mode has actually run."""
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
            "candidate_floor": 175000,
        },
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 195000,
              "employer_authority_limit": 195000},
    )
    # A human move first — its value must never appear in SessionView.
    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "counter", "value": 170000},
    )
    view_before = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token}).json()
    assert view_before["history"][0]["value"] is None
    assert "170000" not in json.dumps(view_before)

    from app.offercheck import store as offercheck_store
    from app.offercheck.agents import mediator as mediator_module
    session = offercheck_store.get_session(session_id)
    candidate_agent, employer_agent = mediator_module.build_agents(session)
    emp_effect = _scripted([{"action": "accept", "value": 185000, "reasoning": "fine"}])
    cand_effect = _scripted([{"action": "counter", "value": 185000, "reasoning": "x"}])
    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect), \
         patch("app.offercheck.agents.mediator.build_agents", return_value=(candidate_agent, employer_agent)):
        client.post(f"/api/offercheck/sessions/{session_id}/start-agentic", json={"token": candidate_token})

    view_after = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token}).json()
    # The pre-agentic human round still has no value (it never crossed the agent boundary)...
    assert view_after["history"][0]["value"] is None
    # ...but the agentic rounds now do, since session.agentic_mode flips true for the whole session.
    agentic_rounds = view_after["history"][1:]
    assert len(agentic_rounds) > 0
    assert any(r["value"] is not None for r in agentic_rounds)


def test_my_agentic_sealed_flag_is_per_viewer(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
            "candidate_floor": 175000,
        },
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    cand_view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token}).json()
    emp_view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": employer_token}).json()
    assert cand_view["my_agentic_sealed"] is True   # candidate sealed at creation
    assert emp_view["my_agentic_sealed"] is False   # employer hasn't sealed anything yet


# ---------------------------------------------------------------------------
# PATCH .../candidate/enable-agentic and .../employer/enable-agentic
# ---------------------------------------------------------------------------

def _unsealed_session_via_http(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
        },
    )
    return submit.json()


def test_enable_candidate_agentic_succeeds(client):
    body = _unsealed_session_via_http(client)
    resp = client.patch(
        f"/api/offercheck/sessions/{body['session_id']}/candidate/enable-agentic",
        json={"token": body["candidate_token"], "candidate_floor": 175000, "candidate_priorities": "base matters"},
    )
    assert resp.status_code == 200
    assert resp.json()["my_agentic_sealed"] is True
    assert "175000" not in resp.text


def test_enable_candidate_agentic_wrong_token_403(client):
    body = _unsealed_session_via_http(client)
    resp = client.patch(
        f"/api/offercheck/sessions/{body['session_id']}/candidate/enable-agentic",
        json={"token": "wrong-token", "candidate_floor": 175000},
    )
    assert resp.status_code == 403


def test_enable_candidate_agentic_already_sealed_409(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 40000, "bonus": 15000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
            "candidate_floor": 175000,
        },
    )
    body = submit.json()
    resp = client.patch(
        f"/api/offercheck/sessions/{body['session_id']}/candidate/enable-agentic",
        json={"token": body["candidate_token"], "candidate_floor": 180000},
    )
    assert resp.status_code == 409


def test_enable_candidate_agentic_terminal_session_409(client):
    body = _unsealed_session_via_http(client)
    client.post(
        f"/api/offercheck/sessions/{body['session_id']}/employer/band",
        json={"employer_token": body["employer_token"], "band_min": 155000, "band_mid": 175000, "band_max": 195000},
    )
    client.post(
        f"/api/offercheck/sessions/{body['session_id']}/employer/move",
        json={"token": body["employer_token"], "move": "walk"},
    )
    resp = client.patch(
        f"/api/offercheck/sessions/{body['session_id']}/candidate/enable-agentic",
        json={"token": body["candidate_token"], "candidate_floor": 175000},
    )
    assert resp.status_code == 409


def test_enable_employer_agentic_succeeds(client):
    body = _unsealed_session_via_http(client)
    client.post(
        f"/api/offercheck/sessions/{body['session_id']}/employer/band",
        json={"employer_token": body["employer_token"], "band_min": 155000, "band_mid": 175000, "band_max": 195000},
    )
    resp = client.patch(
        f"/api/offercheck/sessions/{body['session_id']}/employer/enable-agentic",
        json={"token": body["employer_token"], "employer_authority_limit": 195000},
    )
    assert resp.status_code == 200
    assert resp.json()["my_agentic_sealed"] is True
    assert "195000" not in resp.text


def test_enable_employer_agentic_before_band_set_412(client):
    body = _unsealed_session_via_http(client)
    resp = client.patch(
        f"/api/offercheck/sessions/{body['session_id']}/employer/enable-agentic",
        json={"token": body["employer_token"], "employer_authority_limit": 195000},
    )
    assert resp.status_code == 412


def test_enable_employer_agentic_wrong_token_403(client):
    body = _unsealed_session_via_http(client)
    resp = client.patch(
        f"/api/offercheck/sessions/{body['session_id']}/employer/enable-agentic",
        json={"token": "wrong-token", "employer_authority_limit": 195000},
    )
    assert resp.status_code == 403


def test_enable_employer_agentic_already_sealed_409(client):
    body = _unsealed_session_via_http(client)
    client.post(
        f"/api/offercheck/sessions/{body['session_id']}/employer/band",
        json={"employer_token": body["employer_token"], "band_min": 155000, "band_mid": 175000, "band_max": 195000,
              "employer_authority_limit": 195000},
    )
    resp = client.patch(
        f"/api/offercheck/sessions/{body['session_id']}/employer/enable-agentic",
        json={"token": body["employer_token"], "employer_authority_limit": 200000},
    )
    assert resp.status_code == 409


def test_post_creation_opt_in_reaches_agentic_ready_and_runs(client):
    """Full FIX 2 flow: neither side seals anything at creation/band time — both opt in later
    via PATCH, agentic_ready flips true, and start-agentic runs exactly as if sealed up front."""
    body = _unsealed_session_via_http(client)
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 195000},
    )
    pre = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token}).json()
    assert pre["agentic_ready"] is False

    client.patch(
        f"/api/offercheck/sessions/{session_id}/candidate/enable-agentic",
        json={"token": candidate_token, "candidate_floor": 175000},
    )
    client.patch(
        f"/api/offercheck/sessions/{session_id}/employer/enable-agentic",
        json={"token": employer_token, "employer_authority_limit": 195000},
    )
    post = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token}).json()
    assert post["agentic_ready"] is True

    from app.offercheck import store as offercheck_store
    from app.offercheck.agents import mediator as mediator_module
    session = offercheck_store.get_session(session_id)
    candidate_agent, employer_agent = mediator_module.build_agents(session)
    emp_effect = _scripted([{"action": "accept", "value": 190000, "reasoning": "fine"}])
    cand_effect = _scripted([{"action": "counter", "value": 190000, "reasoning": "x"}])
    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect), \
         patch("app.offercheck.agents.mediator.build_agents", return_value=(candidate_agent, employer_agent)):
        resp = client.post(f"/api/offercheck/sessions/{session_id}/start-agentic", json={"token": candidate_token})

    assert resp.status_code == 200
    assert resp.json()["state"] == "AGREED"
