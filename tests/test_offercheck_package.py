"""
Tests for Offer Check Phase 2B — full compensation package negotiation
(offercheck_phase2_spec.md). Mirrors tests/test_offercheck_agentic.py's
structure and mocking pattern throughout.

Covers:
  - package.py: total_comp_value formula, is_converged threshold, hard
    clamps (candidate floor, employer budget/base range), normalize_package
  - package state machine: PackageNotReady, turn order, max-rounds-expiry,
    accept binds package_agreed correctly
  - PackageCandidateAgent / PackageEmployerAgent: hard clamps enforced in
    code even when the LLM violates them
  - package_mediator: full negotiation converges, reasoning never crosses
    the boundary, walkaway path, spend cap propagation
  - credential.compute_package_credential: terminal-state guard, genuine
    negotiation on clean convergence, capitulation detection on total comp
  - HTTP e2e: package_agentic_ready flag, 412 before sealed, full mocked
    run end to end, auth gate reused from Phase 2A/magic-link work
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.offercheck import credential, demo_auth, negotiation, package, rate_limit, store, verifier
from app.offercheck.agents import package_mediator
from app.offercheck.agents.package_candidate_agent import PackageCandidateAgent
from app.offercheck.agents.package_employer_agent import PackageEmployerAgent
from app.offercheck.schemas import CompetingOffer


@pytest.fixture(autouse=True)
def _clear_state():
    store.reset()
    demo_auth.reset()
    rate_limit.reset()
    yield
    store.reset()
    demo_auth.reset()
    rate_limit.reset()


def _plausible_offer(**overrides):
    defaults = dict(
        company="Stripe", role="Senior Software Engineer", base_salary=180_000,
        equity_value=40_000, bonus=15_000, start_date="2026-09-01",
    )
    defaults.update(overrides)
    return CompetingOffer(**defaults)


def _package(**overrides):
    defaults = dict(
        base=180_000.0, equity_grant=150_000.0, vesting_years=4.0, cliff_months=12.0,
        signing_bonus=20_000.0, annual_bonus_pct=10.0, remote="hybrid",
        start_date_days=30.0, pto_days=15.0,
    )
    defaults.update(overrides)
    return defaults


def _mock_response(payload: dict):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    return msg


def _scripted(responses: list[dict]):
    calls = {"n": 0}

    async def _side_effect(*args, **kwargs):
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return _mock_response(responses[i])

    return _side_effect


# ---------------------------------------------------------------------------
# package.py — math + clamps
# ---------------------------------------------------------------------------

def test_total_comp_value_formula():
    pkg = _package(base=200_000, annual_bonus_pct=10, equity_grant=200_000, vesting_years=4, signing_bonus=20_000)
    # 200000 + 0.10*200000 + 200000/4 + 20000 = 200000 + 20000 + 50000 + 20000 = 290000
    assert package.total_comp_value(pkg) == 290_000


def test_total_comp_value_defaults_vesting_to_one_year_if_zero():
    pkg = _package(base=100_000, equity_grant=50_000, vesting_years=0, annual_bonus_pct=0, signing_bonus=0)
    assert package.total_comp_value(pkg) == 150_000  # equity/1 not equity/0


def test_is_converged_within_threshold():
    assert package.is_converged(200_000, 198_000) is True  # 1% apart
    assert package.is_converged(200_000, 190_000) is False  # ~5% apart


def test_clamp_candidate_package_raises_base_to_floor():
    pkg = _package(base=150_000)
    clamped = package.clamp_candidate_package(pkg, base_floor=175_000, total_comp_floor=0)
    assert clamped["base"] == 175_000


def test_clamp_candidate_package_tops_up_signing_bonus_for_total_comp_floor():
    pkg = _package(base=175_000, equity_grant=0, annual_bonus_pct=0, signing_bonus=0)
    clamped = package.clamp_candidate_package(pkg, base_floor=175_000, total_comp_floor=200_000)
    assert package.total_comp_value(clamped) >= 200_000
    assert clamped["signing_bonus"] == 25_000


def test_clamp_employer_package_clamps_base_into_range():
    pkg = _package(base=250_000)
    clamped = package.clamp_employer_package(pkg, base_min=150_000, base_max=200_000, total_comp_budget=10_000_000)
    assert clamped["base"] == 200_000


def test_clamp_employer_package_trims_signing_bonus_for_budget():
    pkg = _package(base=180_000, equity_grant=0, annual_bonus_pct=0, signing_bonus=50_000)
    clamped = package.clamp_employer_package(pkg, base_min=100_000, base_max=200_000, total_comp_budget=200_000)
    assert package.total_comp_value(clamped) <= 200_000
    assert clamped["signing_bonus"] == 20_000


def test_normalize_package_fills_missing_fields_from_fallback():
    fallback = _package()
    normalized = package.normalize_package({"base": 190_000}, fallback)
    assert normalized["base"] == 190_000
    assert normalized["equity_grant"] == fallback["equity_grant"]


def test_normalize_package_defaults_invalid_remote():
    fallback = _package(remote="hybrid")
    normalized = package.normalize_package({"base": 190_000, "remote": "on-mars"}, fallback)
    assert normalized["remote"] == "hybrid"


def test_normalize_package_handles_non_numeric_fields():
    fallback = _package(base=175_000)
    normalized = package.normalize_package({"base": "not-a-number"}, fallback)
    assert normalized["base"] == 175_000


# ---------------------------------------------------------------------------
# package state machine
# ---------------------------------------------------------------------------

def _sealed_package_session(
    candidate_ask=190_000.0,
    candidate_package_ask=None,
    candidate_total_comp_floor=250_000.0,
    band=(155_000.0, 175_000.0, 200_000.0),
    employer_total_comp_budget=300_000.0,
):
    consistency = verifier.check_consistency(_plausible_offer(), candidate_ask)
    session = store.create_session(
        _plausible_offer(), candidate_ask, consistency,
        candidate_package_ask=candidate_package_ask or _package(base=190_000),
        candidate_total_comp_floor=candidate_total_comp_floor,
    )
    negotiation.set_employer_band(session, *band)
    session.employer_total_comp_budget = employer_total_comp_budget
    return session


def test_build_package_agents_not_ready_without_candidate_package_ask():
    consistency = verifier.check_consistency(_plausible_offer(), 190_000.0)
    session = store.create_session(_plausible_offer(), 190_000.0, consistency)
    negotiation.set_employer_band(session, 155_000, 175_000, 200_000)
    session.employer_total_comp_budget = 300_000.0
    with pytest.raises(package.PackageNotReady):
        package_mediator.build_package_agents(session)


def test_build_package_agents_not_ready_without_employer_budget():
    session = _sealed_package_session()
    session.employer_total_comp_budget = None
    with pytest.raises(package.PackageNotReady):
        package_mediator.build_package_agents(session)


def test_apply_package_move_enforces_turn_order():
    session = _sealed_package_session()
    with pytest.raises(ValueError):
        package.apply_package_move(session, actor="candidate", move="accept", package=None)


def test_apply_package_move_accept_binds_agreed_package():
    session = _sealed_package_session()
    offer_pkg = _package(base=185_000)
    package.apply_package_move(session, actor="employer", move="counter", package=offer_pkg)
    package.apply_package_move(session, actor="candidate", move="accept", package=None)
    assert session.package_state == "AGREED"
    assert session.package_agreed == offer_pkg


def test_apply_package_move_max_rounds_then_expire():
    session = _sealed_package_session()
    for i in range(5):
        actor = "employer" if i % 2 == 0 else "candidate"
        package.apply_package_move(session, actor=actor, move="counter", package=_package(base=180_000 + i * 1000))
    assert session.package_round_number == 5
    assert session.package_state == "EXPIRED"


# ---------------------------------------------------------------------------
# PackageCandidateAgent / PackageEmployerAgent — hard clamps
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_package_candidate_agent_clamps_base_to_floor():
    agent = PackageCandidateAgent(opening_package=_package(base=190_000), base_floor=185_000, total_comp_floor=0)
    low_pkg = _package(base=150_000)
    with patch.object(agent.client.messages, "create", side_effect=_scripted([{"action": "counter", "package": low_pkg, "reasoning": "x"}])):
        result = await agent.decide(employer_package=_package(base=170_000), history=[])
    assert result["package"]["base"] == 185_000


@pytest.mark.asyncio
async def test_package_employer_agent_clamps_base_into_range():
    agent = PackageEmployerAgent(base_min=150_000, base_max=195_000, total_comp_budget=10_000_000)
    high_pkg = _package(base=250_000)
    with patch.object(agent.client.messages, "create", side_effect=_scripted([{"action": "counter", "package": high_pkg, "reasoning": "x"}])):
        result = await agent.decide(candidate_package=_package(base=210_000), history=[])
    assert result["package"]["base"] == 195_000


@pytest.mark.asyncio
async def test_package_agent_normalises_unexpected_action():
    agent = PackageCandidateAgent(opening_package=_package(base=190_000), base_floor=175_000, total_comp_floor=0)
    with patch.object(agent.client.messages, "create", side_effect=_scripted([{"action": "reject", "package": _package()}])):
        result = await agent.decide(employer_package=_package(), history=[])
    assert result["action"] == "counter"


def test_candidate_agent_message_includes_convergence_hint_when_true():
    agent = PackageCandidateAgent(opening_package=_package(base=190_000), base_floor=175_000, total_comp_floor=0)
    messages = agent._build_messages([], _package(), converged_hint=True)
    assert "within 2%" in messages[-1]["content"]


def test_candidate_agent_message_omits_convergence_hint_when_false():
    agent = PackageCandidateAgent(opening_package=_package(base=190_000), base_floor=175_000, total_comp_floor=0)
    messages = agent._build_messages([], _package(), converged_hint=False)
    assert "within 2%" not in messages[-1]["content"]


# ---------------------------------------------------------------------------
# package_mediator
# ---------------------------------------------------------------------------

def test_currently_converged_true_within_threshold():
    session = _sealed_package_session()
    session.candidate_current_package = _package(base=200_000, equity_grant=0, signing_bonus=0, annual_bonus_pct=0)
    session.employer_current_package = _package(base=198_000, equity_grant=0, signing_bonus=0, annual_bonus_pct=0)
    assert package_mediator._currently_converged(session) is True


def test_currently_converged_false_before_employer_has_moved():
    session = _sealed_package_session()
    assert session.employer_current_package is None
    assert package_mediator._currently_converged(session) is False


@pytest.mark.asyncio
async def test_mediator_passes_convergence_hint_to_agents():
    session = _sealed_package_session(candidate_total_comp_floor=0, employer_total_comp_budget=10_000_000)
    candidate_agent, employer_agent = package_mediator.build_package_agents(session)

    # Round 1: employer opens close to the candidate's ask so round 2 should be flagged converged.
    close_pkg = _package(base=189_000, equity_grant=150_000, signing_bonus=20_000, annual_bonus_pct=10)
    emp_effect = _scripted([{"action": "counter", "package": close_pkg, "reasoning": "x"}])
    cand_create = AsyncMock(side_effect=_scripted([{"action": "accept", "package": None, "reasoning": "x"}]))

    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", cand_create):
        await package_mediator.run_package_negotiation(session, candidate_agent, employer_agent)

    second_call_content = cand_create.call_args_list[0].kwargs["messages"][-1]["content"]
    assert "within 2%" in second_call_content

@pytest.mark.asyncio
async def test_package_negotiation_converges_to_agreed():
    session = _sealed_package_session(candidate_total_comp_floor=250_000.0, employer_total_comp_budget=300_000.0)
    candidate_agent, employer_agent = package_mediator.build_package_agents(session)

    emp_effect = _scripted([
        {"action": "counter", "package": _package(base=180_000, equity_grant=140_000, signing_bonus=15_000), "reasoning": "opening"},
        {"action": "accept", "package": None, "reasoning": "good enough"},
    ])
    cand_effect = _scripted([
        {"action": "accept", "package": None, "reasoning": "fine"},
    ])

    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect):
        transcript = await package_mediator.run_package_negotiation(session, candidate_agent, employer_agent)

    assert session.package_state == "AGREED"
    assert session.package_agreed is not None
    assert session.package_agreed["base"] == 180_000
    assert len(transcript) == 2
    assert all("reasoning" not in r for r in transcript)


@pytest.mark.asyncio
async def test_package_negotiation_reasoning_never_crosses_boundary():
    session = _sealed_package_session()
    candidate_agent, employer_agent = package_mediator.build_package_agents(session)

    emp_effect = _scripted([
        {"action": "counter", "package": _package(base=180_000), "reasoning": "EMPLOYER_SECRET_REASONING"},
    ])
    cand_effect = _scripted([
        {"action": "accept", "package": None, "reasoning": "CANDIDATE_SECRET_REASONING"},
    ])

    emp_create = AsyncMock(side_effect=emp_effect)
    cand_create = AsyncMock(side_effect=cand_effect)
    with patch.object(employer_agent.client.messages, "create", emp_create), \
         patch.object(candidate_agent.client.messages, "create", cand_create):
        await package_mediator.run_package_negotiation(session, candidate_agent, employer_agent)

    cand_first_call = cand_create.call_args_list[0].kwargs
    assert "EMPLOYER_SECRET_REASONING" not in json.dumps(cand_first_call["messages"])


@pytest.mark.asyncio
async def test_package_negotiation_walkaway():
    session = _sealed_package_session()
    candidate_agent, employer_agent = package_mediator.build_package_agents(session)

    emp_effect = _scripted([{"action": "walk", "package": None, "reasoning": "too far"}])
    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect):
        transcript = await package_mediator.run_package_negotiation(session, candidate_agent, employer_agent)

    assert session.package_state == "WALKAWAY"
    assert transcript[-1]["move"] == "walk"


@pytest.mark.asyncio
async def test_package_negotiation_surfaces_spend_cap():
    session = _sealed_package_session()
    candidate_agent, employer_agent = package_mediator.build_package_agents(session)

    with patch("app.offercheck.agents.package_mediator.demo_auth.record_and_check_spend",
               side_effect=demo_auth.SpendCapExceeded("cap hit")):
        with pytest.raises(demo_auth.SpendCapExceeded):
            await package_mediator.run_package_negotiation(session, candidate_agent, employer_agent)


# ---------------------------------------------------------------------------
# credential.compute_package_credential
# ---------------------------------------------------------------------------

def test_package_credential_raises_on_non_terminal_session():
    session = _sealed_package_session()
    with pytest.raises(ValueError):
        credential.compute_package_credential(session)


def test_package_credential_genuine_on_clean_convergence():
    session = _sealed_package_session()
    package.apply_package_move(session, actor="employer", move="counter", package=_package(base=180_000))
    package.apply_package_move(session, actor="candidate", move="accept", package=None)
    cred = credential.compute_package_credential(session)
    assert cred.genuine_negotiation is True
    assert cred.outcome == "agreed"


def test_package_credential_detects_capitulation():
    session = _sealed_package_session(
        candidate_package_ask=_package(base=190_000, equity_grant=500_000, signing_bonus=0),
        employer_total_comp_budget=2_000_000.0,
    )
    package.apply_package_move(session, actor="employer", move="counter", package=_package(base=180_000, equity_grant=0, signing_bonus=0))
    # Candidate capitulates from a huge equity ask straight down to the employer's low package.
    package.apply_package_move(session, actor="candidate", move="counter", package=_package(base=180_000, equity_grant=0, signing_bonus=0))
    package.apply_package_move(session, actor="employer", move="accept", package=None)
    cred = credential.compute_package_credential(session)
    assert cred.genuine_negotiation is False


# ---------------------------------------------------------------------------
# HTTP e2e
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _submit_package_session_via_http(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={
            "competing_offer": {"company": "Stripe", "role": "Engineer", "base_salary": 180000,
                                 "equity_value": 150000, "bonus": 20000, "start_date": "2026-09-01"},
            "candidate_ask": 190000,
            "candidate_package_ask": _package(base=190000),
            "candidate_total_comp_floor": 250000,
            "candidate_package_priorities": "equity matters more than base",
        },
    )
    body = submit.json()
    return body["session_id"], body["candidate_token"], body["employer_token"]


def test_package_agentic_ready_flag(client):
    session_id, candidate_token, employer_token = _submit_package_session_via_http(client)

    pre = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token})
    assert pre.json()["package_agentic_ready"] is False

    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 200000,
              "employer_total_comp_budget": 300000},
    )

    post = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token})
    assert post.json()["package_agentic_ready"] is True
    assert "250000" not in post.text
    assert "300000" not in post.text


def test_start_agentic_package_412_before_sealed(client):
    session_id, candidate_token, _ = _submit_package_session_via_http(client)
    resp = client.post(
        f"/api/offercheck/sessions/{session_id}/start-agentic-package",
        json={"token": candidate_token},
    )
    assert resp.status_code == 412


def test_start_agentic_package_requires_auth(client):
    session_id, _, _ = _submit_package_session_via_http(client)
    resp = client.post(f"/api/offercheck/sessions/{session_id}/start-agentic-package", json={})
    assert resp.status_code == 401


def test_start_agentic_package_end_to_end(client):
    session_id, candidate_token, employer_token = _submit_package_session_via_http(client)
    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 200000,
              "employer_total_comp_budget": 300000},
    )

    session = store.get_session(session_id)
    candidate_agent, employer_agent = package_mediator.build_package_agents(session)

    emp_effect = _scripted([{"action": "accept", "package": None, "reasoning": "fine"}])
    cand_effect = _scripted([{"action": "counter", "package": _package(base=190000), "reasoning": "x"}])

    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect), \
         patch("app.offercheck.agents.package_mediator.build_package_agents", return_value=(candidate_agent, employer_agent)):
        resp = client.post(
            f"/api/offercheck/sessions/{session_id}/start-agentic-package",
            json={"token": candidate_token},
        )

    assert resp.status_code == 200
    result = resp.json()
    assert result["state"] == "AGREED"
    assert result["agreed_package"]["base"] == 190000
    assert result["credential"]["genuine_negotiation"] is True
    assert result["attestation"].startswith("sim_quote:")
    assert "155000" not in resp.text  # band never leaks
    assert "reasoning" not in resp.text


def test_session_view_reflects_package_progress_after_agentic_run(client):
    """
    Regression test for a real bug found during live Phala deploy testing: SessionView
    used to expose only the scalar state/turn/round_number fields, which apply_package_move()
    never touches (it mutates package_state/package_round_number instead — see package.py's
    module docstring). A party polling GET /sessions/{id} during/after a package AI negotiation
    saw no progress at all — stuck on whatever the scalar state was before the package run,
    even once the package negotiation had already reached AGREED. package_state/package_turn/
    package_history/package_agreed_package on SessionView fix that; this test locks it in.
    """
    session_id, candidate_token, employer_token = _submit_package_session_via_http(client)
    client.post(
        f"/api/offercheck/sessions/{session_id}/employer/band",
        json={"employer_token": employer_token, "band_min": 155000, "band_mid": 175000, "band_max": 200000,
              "employer_total_comp_budget": 300000},
    )

    pre = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": employer_token}).json()
    assert pre["package_state"] == "PENDING_EMPLOYER"
    assert pre["package_round_number"] == 0
    assert pre["package_history"] == []
    assert pre["package_agreed_package"] is None

    session = store.get_session(session_id)
    candidate_agent, employer_agent = package_mediator.build_package_agents(session)
    emp_effect = _scripted([{"action": "accept", "package": None, "reasoning": "fine"}])
    cand_effect = _scripted([{"action": "counter", "package": _package(base=190000), "reasoning": "x"}])
    with patch.object(employer_agent.client.messages, "create", side_effect=emp_effect), \
         patch.object(candidate_agent.client.messages, "create", side_effect=cand_effect), \
         patch("app.offercheck.agents.package_mediator.build_package_agents", return_value=(candidate_agent, employer_agent)):
        client.post(f"/api/offercheck/sessions/{session_id}/start-agentic-package", json={"token": candidate_token})

    # The scalar (base-salary-only) channel never ran, so it must stay untouched at PENDING_EMPLOYER —
    # a UI naively reading view.state/view.turn alone would still see no progress, which is exactly
    # why the frontend now checks package_round_number > 0 to decide which channel is authoritative.
    post_employer = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": employer_token}).json()
    assert post_employer["state"] == "PENDING_EMPLOYER"
    assert post_employer["package_state"] == "AGREED"
    assert post_employer["package_turn"] is None  # terminal
    assert post_employer["package_round_number"] >= 1
    assert len(post_employer["package_history"]) == post_employer["package_round_number"]
    assert post_employer["package_agreed_package"]["base"] == 190000
    # Package rounds are agentic-only by construction (see PackageRoundDetail's docstring) —
    # every round's package + total_comp is safe to expose to both parties unconditionally.
    assert all(r["package"] is not None and r["total_comp"] is not None for r in post_employer["package_history"])

    # Both parties see the identical package_state/package_history — same shared server-side truth.
    post_candidate = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token}).json()
    assert post_candidate["package_state"] == post_employer["package_state"]
    assert post_candidate["package_history"] == post_employer["package_history"]
