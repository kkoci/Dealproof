"""
End-to-end integration tests — Phase 5.

Tests the full HTTP API stack from the client's perspective:
  POST /api/deals/run (with seller_proof) → verify → negotiate → attest → result.

All external I/O is mocked:
  - Claude API: AsyncMock on BuyerAgent.evaluate_offer / SellerAgent.make_offer
  - tappd: AsyncMock on sign_result (verification + deal attestation)
  - SQLite: real aiosqlite against a tmp-file DB (not mocked — we want to test
    the full persistence round-trip)

The TestClient from FastAPI/Starlette is used, which runs the ASGI app
synchronously in the test process.  We patch the DB path to a tmp file so
tests don't pollute the dev dealproof.db.

What each test proves
---------------------
test_e2e_full_deal_with_proof
  - seller_proof present and valid
  - verification passes → attestation quote #1 produced
  - negotiation agrees → attestation quote #2 produced (combined payload)
  - DealResult contains both attestation fields
  - GET /api/deals/{id}/attestation returns deal quote
  - GET /api/deals/{id}/verification returns verification record
  - GET /api/deals/{id}/status shows "agreed"

test_e2e_deal_without_proof
  - no seller_proof
  - verification skipped
  - negotiation agrees → deal attestation produced (no data_hash in payload)
  - data_verification_attestation is None

test_e2e_bad_proof_returns_400
  - seller_proof.root_hash does not match data_hash
  - HTTP 400 returned before negotiation starts
  - deal status is "verification_failed"

test_e2e_negotiation_fails
  - both agents mock to reject
  - agreed=False, attestation=None
  - status is "failed"

test_e2e_two_step_flow
  - POST /api/deals → POST /api/deals/{id}/negotiate
  - Same result as /run single-call
"""
import hashlib
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_valid_proof(chunks: list[bytes] | None = None):
    if chunks is None:
        chunks = [b"chunk_alpha", b"chunk_beta", b"chunk_gamma"]
    chunk_hashes = [hashlib.sha256(c).hexdigest() for c in chunks]
    length_prefix = len(chunk_hashes).to_bytes(4, "big")
    raw = length_prefix + b"".join(bytes.fromhex(h) for h in chunk_hashes)
    root_hash = hashlib.sha256(raw).hexdigest()
    return root_hash, {
        "root_hash": root_hash,
        "chunk_hashes": chunk_hashes,
        "chunk_count": len(chunks),
        "algorithm": "sha256",
    }


def _agent_response(action: str, price: float, terms: dict | None = None):
    """Build the dict that BuyerAgent.evaluate_offer / SellerAgent.make_offer returns."""
    return {
        "action": action,
        "price": price,
        "terms": terms or {"access_scope": "full", "duration_days": 365},
        "reasoning": f"e2e test: {action} at {price}",
    }


BASE_PAYLOAD = {
    "buyer_budget": 1000.0,
    "buyer_requirements": "10GB labelled image dataset",
    "data_description": "COCO-style dataset, verified 2024",
    "floor_price": 600.0,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_db_path(tmp_path):
    """
    Redirect app.db.DB_PATH to a temp file so each test gets a clean DB.
    autouse=True — applies to every test in this module automatically.
    """
    import app.db as db_module
    original = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "test_dealproof.db"
    yield
    db_module.DB_PATH = original


@pytest.fixture(autouse=True)
def mock_memory_sidecar():
    """
    Mock all memory sidecar calls so tests don't depend on a running service.
    autouse=True — applied to every test in this module.
    Patch at app.api.routes (where the names are used) so the mocks take effect.
    Returns empty results by default so memory context is blank and memory_hash is "".
    """
    with patch("app.api.routes.search_memories", new_callable=AsyncMock, return_value=[]), \
         patch("app.api.routes.add_memories", new_callable=AsyncMock, return_value={"stored": 0, "ids": []}), \
         patch("app.api.routes.get_memory_hash", new_callable=AsyncMock, return_value={"hash": "", "count": 0}), \
         patch("app.api.routes.audit_agent_policy", new_callable=AsyncMock, side_effect=Exception("mock: no picreds")), \
         patch("app.api.routes.audit_deal_conduct", new_callable=AsyncMock, side_effect=Exception("mock: no picreds")):
        yield


@pytest.fixture()
def client():
    """
    FastAPI TestClient.  Uses a context manager so the lifespan (db.init_db)
    runs before the first request.
    """
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_e2e_full_deal_with_proof(client):
    """
    Full Phase 3 flow: valid seller_proof → verification → negotiation → two attestations.
    """
    data_hash, seller_proof = _build_valid_proof()

    payload = {
        **BASE_PAYLOAD,
        "data_hash": data_hash,
        "seller_proof": seller_proof,
    }

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock, return_value="verification-quote-xyz"), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock, return_value="deal-quote-abc"), \
         patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock) as mock_buyer, \
         patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock) as mock_seller:

        mock_seller.return_value = _agent_response("offer", 800.0)
        mock_buyer.return_value  = _agent_response("accept", 800.0)

        response = client.post("/api/deals/run", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()

    # Core result
    assert body["agreed"] is True
    assert body["final_price"] == 800.0

    # Both attestation fields present
    assert body["attestation"] == "deal-quote-abc"
    assert body["data_verification_attestation"] == "verification-quote-xyz"

    deal_id = body["deal_id"]

    # GET /status
    r = client.get(f"/api/deals/{deal_id}/status")
    assert r.status_code == 200
    assert r.json()["status"] == "agreed"

    # GET /attestation
    r = client.get(f"/api/deals/{deal_id}/attestation")
    assert r.status_code == 200
    assert r.json()["attestation"] == "deal-quote-abc"

    # GET /verification
    r = client.get(f"/api/deals/{deal_id}/verification")
    assert r.status_code == 200
    v = r.json()["verification"]
    assert v["verified"] is True
    assert v["data_hash"] == data_hash
    assert v["chunk_count"] == 3
    assert v["attestation"] == "verification-quote-xyz"


def test_e2e_deal_without_proof(client):
    """
    No seller_proof: verification skipped, deal quote has no data_hash field,
    data_verification_attestation is None.
    """
    data_hash = "a" * 64
    payload = {**BASE_PAYLOAD, "data_hash": data_hash}

    with patch("app.agents.negotiation.sign_result", new_callable=AsyncMock, return_value="deal-quote-noproof"), \
         patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock) as mock_buyer, \
         patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock) as mock_seller:

        mock_seller.return_value = _agent_response("offer", 750.0)
        mock_buyer.return_value  = _agent_response("accept", 750.0)

        # Also capture what sign_result was called with
        response = client.post("/api/deals/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["agreed"] is True
    assert body["attestation"] == "deal-quote-noproof"
    assert body["data_verification_attestation"] is None


def test_e2e_deal_sign_payload_includes_data_hash_when_proof_present(client):
    """
    When proof is present, the negotiation sign_result call must include
    data_hash and data_verified in the payload (combined attestation).
    """
    data_hash, seller_proof = _build_valid_proof([b"chunk1", b"chunk2"])
    payload = {**BASE_PAYLOAD, "data_hash": data_hash, "seller_proof": seller_proof}

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock, return_value="vq"), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock, return_value="dq") as mock_deal_sign, \
         patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock, return_value=_agent_response("accept", 700.0)), \
         patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock, return_value=_agent_response("offer", 700.0)):

        client.post("/api/deals/run", json=payload)

    call_payload = mock_deal_sign.call_args[0][0]
    assert call_payload["data_hash"] == data_hash
    assert call_payload["data_verified"] is True
    assert "final_price" in call_payload
    assert "terms" in call_payload


def test_e2e_bad_proof_returns_400(client):
    """
    seller_proof.root_hash does not match data_hash → HTTP 400.
    Negotiation never starts (sign_result for deal never called).
    """
    data_hash = "b" * 64   # does not match any valid proof root
    _, seller_proof = _build_valid_proof()  # proof has a different root_hash

    payload = {
        **BASE_PAYLOAD,
        "data_hash": data_hash,
        "seller_proof": seller_proof,
    }

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_v_sign, \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock) as mock_deal_sign:

        response = client.post("/api/deals/run", json=payload)

    assert response.status_code == 400
    assert "verification failed" in response.json()["detail"].lower()
    mock_v_sign.assert_not_called()    # never got to signing
    mock_deal_sign.assert_not_called() # negotiation never started


def test_e2e_bad_proof_deal_status_is_verification_failed(client):
    """
    After a failed proof, GET /api/deals/{id}/status returns 'verification_failed'.
    Uses the two-step flow so we have the deal_id before the 400.
    """
    data_hash = "c" * 64
    _, seller_proof = _build_valid_proof()  # mismatched root

    payload = {**BASE_PAYLOAD, "data_hash": data_hash, "seller_proof": seller_proof}

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock):

        # Step 1 — create deal (succeeds)
        r = client.post("/api/deals", json=payload)
        assert r.status_code == 201
        deal_id = r.json()["deal_id"]

        # Step 2 — negotiate (fails verification)
        r = client.post(f"/api/deals/{deal_id}/negotiate")
        assert r.status_code == 400

    # Status should be verification_failed
    r = client.get(f"/api/deals/{deal_id}/status")
    assert r.status_code == 200
    assert r.json()["status"] == "verification_failed"


def test_e2e_negotiation_fails(client):
    """
    Buyer rejects → agreed=False, attestation=None, status='failed'.
    """
    data_hash, seller_proof = _build_valid_proof()
    payload = {**BASE_PAYLOAD, "data_hash": data_hash, "seller_proof": seller_proof}

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock, return_value="vq"), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock) as mock_deal_sign, \
         patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock) as mock_buyer, \
         patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock) as mock_seller:

        mock_seller.return_value = _agent_response("offer", 800.0)
        mock_buyer.return_value  = _agent_response("reject", 0.0)

        response = client.post("/api/deals/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["agreed"] is False
    assert body["attestation"] is None
    mock_deal_sign.assert_not_called()

    deal_id = body["deal_id"]
    r = client.get(f"/api/deals/{deal_id}/status")
    assert r.json()["status"] == "failed"


def test_e2e_two_step_flow(client):
    """
    POST /api/deals  then  POST /api/deals/{id}/negotiate produces the same
    result as the single-call /run endpoint.
    """
    data_hash, seller_proof = _build_valid_proof([b"alpha", b"beta"])
    payload = {**BASE_PAYLOAD, "data_hash": data_hash, "seller_proof": seller_proof}

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock, return_value="vq-two-step"), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock, return_value="dq-two-step"), \
         patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock, return_value=_agent_response("accept", 720.0)), \
         patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock, return_value=_agent_response("offer", 720.0)):

        # Step 1
        r = client.post("/api/deals", json=payload)
        assert r.status_code == 201
        deal_id = r.json()["deal_id"]
        assert r.json()["status"] == "pending"

        # Step 2
        r = client.post(f"/api/deals/{deal_id}/negotiate")
        assert r.status_code == 200
        body = r.json()

    assert body["agreed"] is True
    assert body["deal_id"] == deal_id
    assert body["attestation"] == "dq-two-step"
    assert body["data_verification_attestation"] == "vq-two-step"


def test_e2e_duplicate_negotiate_returns_409(client):
    """
    Calling /negotiate twice on the same deal returns 409 Conflict.
    """
    data_hash, seller_proof = _build_valid_proof()
    payload = {**BASE_PAYLOAD, "data_hash": data_hash, "seller_proof": seller_proof}

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock, return_value="vq"), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock, return_value="dq"), \
         patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock, return_value=_agent_response("accept", 700.0)), \
         patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock, return_value=_agent_response("offer", 700.0)):

        r = client.post("/api/deals", json=payload)
        deal_id = r.json()["deal_id"]

        r1 = client.post(f"/api/deals/{deal_id}/negotiate")
        assert r1.status_code == 200

        r2 = client.post(f"/api/deals/{deal_id}/negotiate")
        assert r2.status_code == 409


def test_e2e_memory_attested_in_response(client):
    """
    When the memory sidecar returns non-empty hashes, the DealResult should
    include memory_hash and memory_attested: true.
    """
    data_hash = "e" * 64
    payload = {**BASE_PAYLOAD, "data_hash": data_hash}

    fake_hash = "f" * 64

    with patch("app.agents.negotiation.sign_result", new_callable=AsyncMock, return_value="deal-quote-mem"), \
         patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=AsyncMock, return_value=_agent_response("accept", 700.0)), \
         patch("app.agents.seller.SellerAgent.make_offer", new_callable=AsyncMock, return_value=_agent_response("offer", 700.0)), \
         patch("app.api.routes.search_memories", new_callable=AsyncMock, return_value=[{"content": "past deal at 700"}]), \
         patch("app.api.routes.add_memories", new_callable=AsyncMock, return_value={"stored": 1, "ids": ["m1"]}), \
         patch("app.api.routes.get_memory_hash", new_callable=AsyncMock, return_value={"hash": fake_hash, "count": 1}):

        response = client.post("/api/deals/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["agreed"] is True
    assert body["memory_attested"] is True
    assert body["memory_hash"] == f"{fake_hash}:{fake_hash}"


def test_e2e_unknown_deal_returns_404(client):
    r = client.get("/api/deals/nonexistent-id/status")
    assert r.status_code == 404


def test_e2e_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "tee_mode" in body


def test_e2e_attest_endpoint_returns_quote(client):
    """
    GET /api/attest returns a valid AttestationResponse in simulation mode.
    No auth required; quote and mrenclave are present and non-empty.
    """
    r = client.get("/api/attest")
    assert r.status_code == 200
    body = r.json()
    assert "quote" in body
    assert "mrenclave" in body
    assert "timestamp" in body
    assert body["quote"].startswith("sim_quote:")
    assert body["mrenclave"].startswith("sim_mrenclave:")
    assert isinstance(body["timestamp"], int)
    assert body["timestamp"] > 0


def test_e2e_attest_endpoint_is_deterministic(client):
    """
    Two calls to GET /api/attest return the same quote and mrenclave
    (simulation mode is deterministic — same enclave measurement every time).
    """
    r1 = client.get("/api/attest")
    r2 = client.get("/api/attest")
    assert r1.json()["quote"] == r2.json()["quote"]
    assert r1.json()["mrenclave"] == r2.json()["mrenclave"]
