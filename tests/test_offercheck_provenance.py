"""
Tests for app.offercheck.provenance and the endpoints/gate built around it
(vertical/hr-offer-check): a candidate can prove real git-commit history behind
their claimed experience via POST .../candidate/verify-credential, and an
employer can require it before the candidate is allowed to move (see
EmployerInviteRequest.require_provenance_credential and
negotiation.apply_move()'s gate). See CLAUDE.md's "Offer Check Architecture"
and app/offercheck/provenance.py's module docstring for the design.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.offercheck import auth, invites, rate_limit, store

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
# Fake GitHub — same shape as tests/test_devcred.py's _FakeGithubAsyncClient,
# since app.offercheck.provenance reuses app.devcred's fetch pipeline verbatim.
# ---------------------------------------------------------------------------

def _github_commit_item(sha: str, date: str) -> dict:
    return {
        "sha": sha,
        "commit": {"author": {"name": "octocat", "date": date}, "message": f"feat: implement {sha}"},
        "parents": [1],
    }


def _make_github_response(json_data, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


class _FakeGithubAsyncClient:
    """Single-branch, two-commit repo — enough to exercise the pipeline without
    needing to assert an exact seniority_signal (that's git_inspector's own coverage)."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, params=None, timeout=None):
        params = params or {}
        if url.endswith("/branches"):
            if params.get("page", 1) != 1:
                return _make_github_response([])
            return _make_github_response([{"name": "main", "commit": {"sha": "sha-1"}}])
        if url.endswith("/commits"):
            if params.get("page", 1) != 1:
                return _make_github_response([])
            return _make_github_response([
                _github_commit_item("sha-1", "2024-01-01T00:00:00"),
                _github_commit_item("sha-2", "2024-02-01T00:00:00"),
            ])
        # per-commit detail endpoint (enrichment) — skip it in this test
        return _make_github_response({}, status_code=404)


class _EmptyGithubAsyncClient:
    """No branches at all — exercises the "no commits found" 422 path."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, params=None, timeout=None):
        if url.endswith("/branches"):
            return _make_github_response([])
        return _make_github_response({}, status_code=404)


# ---------------------------------------------------------------------------
# POST .../candidate/verify-credential
# ---------------------------------------------------------------------------

def test_verify_credential_returns_summary_and_is_visible_to_both_parties(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185000},
    )
    body = submit.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    with patch("httpx.AsyncClient", return_value=_FakeGithubAsyncClient()):
        resp = client.post(
            f"/api/offercheck/sessions/{session_id}/candidate/verify-credential",
            json={"token": candidate_token, "github_token": "fake-token", "repos": ["octocat/hello-world"]},
        )
    assert resp.status_code == 200
    cred = resp.json()["credential"]
    assert cred["seniority_signal"] in ("junior", "mid", "senior")
    assert cred["total_commits"] == 2

    # Visible to the candidate...
    candidate_view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": candidate_token})
    assert candidate_view.json()["candidate_provenance_verified"] is True
    assert candidate_view.json()["candidate_provenance_credential"]["total_commits"] == 2

    # ...and to the employer — this is evidence meant to be shown, not a sealed number.
    employer_view = client.get(f"/api/offercheck/sessions/{session_id}", params={"token": employer_token})
    assert employer_view.json()["candidate_provenance_verified"] is True
    assert employer_view.json()["candidate_provenance_credential"]["total_commits"] == 2


def test_verify_credential_wrong_token_rejected(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185000},
    )
    session_id = submit.json()["session_id"]

    resp = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/verify-credential",
        json={"token": "not-a-real-token", "github_token": "fake-token", "repos": ["octocat/hello-world"]},
    )
    assert resp.status_code == 403


def test_verify_credential_rejects_malformed_repo_name(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185000},
    )
    body = submit.json()

    resp = client.post(
        f"/api/offercheck/sessions/{body['session_id']}/candidate/verify-credential",
        json={"token": body["candidate_token"], "github_token": "fake-token", "repos": ["not-a-valid-repo"]},
    )
    assert resp.status_code == 400


def test_verify_credential_no_commits_returns_422(client):
    submit = client.post(
        "/api/offercheck/sessions",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185000},
    )
    body = submit.json()

    with patch("httpx.AsyncClient", return_value=_EmptyGithubAsyncClient()):
        resp = client.post(
            f"/api/offercheck/sessions/{body['session_id']}/candidate/verify-credential",
            json={"token": body["candidate_token"], "github_token": "fake-token", "repos": ["octocat/empty-repo"]},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Employer-required gate (EmployerInviteRequest.require_provenance_credential)
# ---------------------------------------------------------------------------

def test_invite_require_provenance_credential_defaults_false_and_passes_through_when_set(client):
    _, api_key = _register_company(client)

    default_invite = client.post(
        "/api/offercheck/employer/new",
        json={"band_min": 155_000, "band_mid": 175_000, "band_max": 195_000},
        headers={"X-API-Key": api_key},
    )
    joined_default = client.post(
        f"/api/offercheck/candidate/join/{default_invite.json()['invite_id']}",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185_000},
    )
    default_view = client.get(
        f"/api/offercheck/sessions/{joined_default.json()['session_id']}",
        params={"token": joined_default.json()["candidate_token"]},
    )
    assert default_view.json()["require_provenance_credential"] is False

    required_invite = client.post(
        "/api/offercheck/employer/new",
        json={"band_min": 155_000, "band_mid": 175_000, "band_max": 195_000, "require_provenance_credential": True},
        headers={"X-API-Key": api_key},
    )
    joined_required = client.post(
        f"/api/offercheck/candidate/join/{required_invite.json()['invite_id']}",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 190_000},
    )
    required_view = client.get(
        f"/api/offercheck/sessions/{joined_required.json()['session_id']}",
        params={"token": joined_required.json()["candidate_token"]},
    )
    assert required_view.json()["require_provenance_credential"] is True


def test_required_credential_blocks_candidate_move_until_verified(client):
    _, api_key = _register_company(client)
    created = client.post(
        "/api/offercheck/employer/new",
        json={"band_min": 155_000, "band_mid": 175_000, "band_max": 195_000, "require_provenance_credential": True},
        headers={"X-API-Key": api_key},
    )
    invite_id = created.json()["invite_id"]

    joined = client.post(
        f"/api/offercheck/candidate/join/{invite_id}",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185_000},
    )
    body = joined.json()
    session_id, candidate_token, employer_token = body["session_id"], body["candidate_token"], body["employer_token"]

    # Band already sealed from the invite -> employer moves first.
    employer_move = client.post(
        f"/api/offercheck/sessions/{session_id}/employer/move",
        json={"token": employer_token, "move": "counter", "value": 170_000},
    )
    assert employer_move.status_code == 200
    assert employer_move.json()["turn"] == "candidate"

    # Candidate's turn, but the employer requires a verified credential first.
    blocked = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/move",
        json={"token": candidate_token, "move": "accept", "value": None},
    )
    assert blocked.status_code == 412

    # Verify, then the same move succeeds.
    with patch("httpx.AsyncClient", return_value=_FakeGithubAsyncClient()):
        verify = client.post(
            f"/api/offercheck/sessions/{session_id}/candidate/verify-credential",
            json={"token": candidate_token, "github_token": "fake-token", "repos": ["octocat/hello-world"]},
        )
    assert verify.status_code == 200

    unblocked = client.post(
        f"/api/offercheck/sessions/{session_id}/candidate/move",
        json={"token": candidate_token, "move": "accept", "value": None},
    )
    assert unblocked.status_code == 200
    assert unblocked.json()["state"] == "PENDING_APPROVAL"


def test_required_credential_does_not_block_employer_moves(client):
    """The gate is candidate-specific — an employer who requires the credential
    from the candidate is not somehow blocked from moving themselves."""
    _, api_key = _register_company(client)
    created = client.post(
        "/api/offercheck/employer/new",
        json={"band_min": 155_000, "band_mid": 175_000, "band_max": 195_000, "require_provenance_credential": True},
        headers={"X-API-Key": api_key},
    )
    joined = client.post(
        f"/api/offercheck/candidate/join/{created.json()['invite_id']}",
        json={"competing_offer": _COMPETING_OFFER, "candidate_ask": 185_000},
    )
    body = joined.json()

    employer_move = client.post(
        f"/api/offercheck/sessions/{body['session_id']}/employer/move",
        json={"token": body["employer_token"], "move": "counter", "value": 170_000},
    )
    assert employer_move.status_code == 200
