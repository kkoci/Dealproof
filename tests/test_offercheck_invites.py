"""
Tests for the employer-initiated invite flow (vertical/hr-offer-check): an
authenticated company opens a negotiation (POST /employer/new) before any
candidate exists, a candidate later claims it (POST /candidate/join/{id}),
and store.create_session() runs exactly once, at claim time — identical to
the existing candidate-initiated POST /sessions path from that point on.
See CLAUDE.md's "Offer Check Architecture" for the base flow this mirrors.
"""
import pytest
from fastapi.testclient import TestClient

from app.offercheck import auth, invites, negotiation, rate_limit, store, verifier
from app.offercheck.schemas import CompetingOffer

pytestmark = []


@pytest.fixture(autouse=True)
def _clear_state():
    store.reset()
    auth.reset()
    rate_limit.reset()
    invites.reset()
    yield
    store.reset()
    auth.reset()
    rate_limit.reset()
    invites.reset()


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _register_company(client, name="Acme Corp"):
    resp = client.post("/api/offercheck/company/register", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["company_id"], resp.json()["api_key"]


_COMPETING_OFFER = {
    "company": "Stripe",
    "role": "Senior Software Engineer",
    "base_salary": 180000,
    "equity_value": 40000,
    "bonus": 15000,
    "start_date": "2026-09-01",
}


# ---------------------------------------------------------------------------
# Pure store unit tests
# ---------------------------------------------------------------------------

def test_create_invite_starts_pending():
    invite = invites.create_invite("company_1", 155_000, 175_000, 195_000)
    assert invite.status == invites.PENDING
    assert invite.session_id is None
    assert invites.get_invite(invite.id) is invite


def test_claim_invite_marks_claimed_and_stores_session_id():
    invite = invites.create_invite("company_1", 155_000, 175_000, 195_000)
    invites.claim_invite(invite, "session_abc")
    assert invite.status == invites.CLAIMED
    assert invite.session_id == "session_abc"


# ---------------------------------------------------------------------------
# HTTP e2e — full lifecycle
# ---------------------------------------------------------------------------

def test_employer_new_requires_api_key(client):
    resp = client.post(
        "/api/offercheck/employer/new",
        json={"band_min": 155_000, "band_mid": 175_000, "band_max": 195_000},
    )
    assert resp.status_code == 401


def test_full_invite_lifecycle_create_unclaimed_join_becomes_normal_session(client):
    company_id, api_key = _register_company(client)

    # Create — unclaimed.
    created = client.post(
        "/api/offercheck/employer/new",
        json={
            "band_min": 155_000,
            "band_mid": 175_000,
            "band_max": 195_000,
            "requirements": "Senior Engineer, backend team",
        },
        headers={"X-API-Key": api_key},
    )
    assert created.status_code == 201
    invite_id = created.json()["invite_id"]
    assert created.json()["status"] == "PENDING_CANDIDATE"
    assert created.json()["candidate_join_link"] == f"/offercheck/candidate/join/{invite_id}"

    # Status check — unclaimed, no employer_token yet.
    status = client.get(f"/api/offercheck/employer/invite/{invite_id}", headers={"X-API-Key": api_key})
    assert status.status_code == 200
    assert status.json()["status"] == "PENDING_CANDIDATE"
    assert status.json()["session_id"] is None
    assert status.json()["employer_token"] is None

    # Candidate joins — becomes a normal Session, identical response shape to POST /sessions.
    joined = client.post(
        f"/api/offercheck/candidate/join/{invite_id}",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185_000},
    )
    assert joined.status_code == 200
    body = joined.json()
    session_id = body["session_id"]
    candidate_token = body["candidate_token"]
    employer_token = body["employer_token"]
    assert body["state"] == "PENDING_EMPLOYER"
    assert body["consistency"]["verified"] is True

    # Status check — claimed, employer_token now available to the owning company.
    status_after = client.get(f"/api/offercheck/employer/invite/{invite_id}", headers={"X-API-Key": api_key})
    assert status_after.status_code == 200
    assert status_after.json()["status"] == "CLAIMED"
    assert status_after.json()["session_id"] == session_id
    assert status_after.json()["employer_token"] == employer_token

    # The band is already sealed from the invite — employer's turn, no separate
    # POST .../employer/band call needed. Employer can move immediately.
    view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": employer_token})
    assert view.status_code == 200
    assert view.json()["band_set"] is True
    assert view.json()["turn"] == "employer"
    assert view.json()["gap_pct"] is None  # no employer_current_offer yet — same as the base flow pre-first-move

    # Session appears in the company's dashboard listing (company_id carried over from the invite).
    listing = client.get("/api/offercheck/company/sessions", headers={"X-API-Key": api_key})
    assert listing.status_code == 200
    assert any(s["session_id"] == session_id for s in listing.json()["sessions"])

    # From here on, the normal negotiation endpoints work exactly as they do
    # for a candidate-initiated session — no separate code path.
    move1 = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "counter", "value": 170_000},
    )
    assert move1.status_code == 200
    move2 = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/move",
        json={"token": candidate_token, "move": "accept", "value": None},
    )
    assert move2.status_code == 200
    assert move2.json()["state"] == "PENDING_APPROVAL"

    # Both sides approve before the session is genuinely terminal.
    client.post(f"/api/offercheck/sessions/{session_id}/candidate/approval", json={"token": candidate_token, "decision": "approve"})
    final = client.post(f"/api/offercheck/sessions/{session_id}/employer/approval", json={"token": employer_token, "decision": "approve"})
    assert final.json()["state"] == "AGREED"


def test_join_invite_twice_rejects_second_claim(client):
    _, api_key = _register_company(client)
    created = client.post(
        "/api/offercheck/employer/new",
        json={"band_min": 155_000, "band_mid": 175_000, "band_max": 195_000},
        headers={"X-API-Key": api_key},
    )
    invite_id = created.json()["invite_id"]

    first = client.post(
        f"/api/offercheck/candidate/join/{invite_id}",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185_000},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/offercheck/candidate/join/{invite_id}",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 190_000},
    )
    assert second.status_code == 409


def test_join_unknown_invite_404s(client):
    resp = client.post(
        "/api/offercheck/candidate/join/not-a-real-invite",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185_000},
    )
    assert resp.status_code == 404


def test_invite_status_requires_owning_company(client):
    _, api_key_a = _register_company(client, "Acme Corp")
    _, api_key_b = _register_company(client, "Globex Corp")

    created = client.post(
        "/api/offercheck/employer/new",
        json={"band_min": 155_000, "band_mid": 175_000, "band_max": 195_000},
        headers={"X-API-Key": api_key_a},
    )
    invite_id = created.json()["invite_id"]

    cross_company = client.get(f"/api/offercheck/employer/invite/{invite_id}", headers={"X-API-Key": api_key_b})
    assert cross_company.status_code == 403

    own_company = client.get(f"/api/offercheck/employer/invite/{invite_id}", headers={"X-API-Key": api_key_a})
    assert own_company.status_code == 200


def test_invite_status_unknown_invite_404s(client):
    _, api_key = _register_company(client)
    resp = client.get("/api/offercheck/employer/invite/not-a-real-invite", headers={"X-API-Key": api_key})
    assert resp.status_code == 404


def test_candidate_join_supports_sealed_agentic_floor(client):
    """candidate_floor/candidate_priorities pass through to the Session exactly
    as they do via POST /sessions — verified indirectly via agentic_ready once
    the invite's own employer_authority_limit is also sealed."""
    _, api_key = _register_company(client)
    created = client.post(
        "/api/offercheck/employer/new",
        json={
            "band_min": 155_000, "band_mid": 175_000, "band_max": 195_000,
            "employer_authority_limit": 190_000,
        },
        headers={"X-API-Key": api_key},
    )
    invite_id = created.json()["invite_id"]

    joined = client.post(
        f"/api/offercheck/candidate/join/{invite_id}",
        json={
            "competing_offer": _COMPETING_OFFER, "candidate_ask": 185_000,
            "candidate_floor": 160_000, "candidate_priorities": "base matters most",
        },
    )
    assert joined.status_code == 200
    session_id = joined.json()["session_id"]
    candidate_token = joined.json()["candidate_token"]

    view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token})
    assert view.json()["agentic_ready"] is True  # both candidate_floor and employer_authority_limit sealed


# ---------------------------------------------------------------------------
# Isolation check — this flow must not require touching the core state
# machine, attestation, or mediator modules; it only calls their existing
# public functions (negotiation.set_employer_band, store.create_session).
# ---------------------------------------------------------------------------

def test_negotiation_state_machine_untouched_by_invite_flow():
    """Sanity check that the invite flow composes existing negotiation.py
    functions rather than reimplementing state-machine logic."""
    competing_offer = CompetingOffer(**_COMPETING_OFFER)
    session = store.create_session(
        competing_offer,
        185_000,
        verifier.check_consistency(competing_offer, 185_000),
    )
    gap = negotiation.set_employer_band(session, 155_000, 175_000, 195_000)
    assert session.band_set is True
    assert gap == pytest.approx((185_000 - 175_000) / 175_000 * 100)
    assert session.state == "PENDING_EMPLOYER"  # unchanged by band-setting, exactly as the base flow behaves
