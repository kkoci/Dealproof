"""
Props data-authenticity verifier tests — Phase 3.

Tests cover every layer of app/props/verifier.py:
  - Pure helpers: _is_valid_sha256_hex, compute_merkle_root,
    validate_proof_structure
  - Main async function: verify_data_authenticity (sign_result mocked)
  - Failure paths: tampered hash, wrong chunk count, invalid format,
    Merkle root mismatch, unsupported algorithm
  - Route-level gate: verification_failed → HTTP 400, negotiation never runs

All tappd calls are mocked via patch on sign_result so tests run without
docker-compose.

Proof construction helper
--------------------------
To build a valid seller_proof for tests:
  1. Pick arbitrary chunk byte strings.
  2. chunk_hashes = [sha256(chunk).hexdigest() for chunk in chunks]
  3. raw = b"".join(bytes.fromhex(h) for h in chunk_hashes)
  4. root_hash = sha256(raw).hexdigest()
  5. data_hash = root_hash   (the advertised hash must equal the root)
  6. seller_proof = {"root_hash": root_hash, "chunk_hashes": chunk_hashes,
                     "chunk_count": len(chunks), "algorithm": "sha256"}
"""
import hashlib
import pytest
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# Test-data factory
# ---------------------------------------------------------------------------

def _build_valid_proof(chunks: list[bytes] | None = None):
    """
    Build a (data_hash, seller_proof) pair that will pass verification.
    If chunks is None, defaults to three small byte strings.
    """
    if chunks is None:
        chunks = [b"dataset_chunk_alpha", b"dataset_chunk_beta", b"dataset_chunk_gamma"]

    chunk_hashes = [hashlib.sha256(c).hexdigest() for c in chunks]
    raw = b"".join(bytes.fromhex(h) for h in chunk_hashes)
    root_hash = hashlib.sha256(raw).hexdigest()

    return root_hash, {
        "root_hash": root_hash,
        "chunk_hashes": chunk_hashes,
        "chunk_count": len(chunks),
        "algorithm": "sha256",
    }


# ---------------------------------------------------------------------------
# Pure helper tests — no I/O, no mocks needed
# ---------------------------------------------------------------------------

def test_compute_merkle_root_deterministic():
    """Same chunk hashes always produce the same root."""
    from app.props.verifier import compute_merkle_root

    hashes = [hashlib.sha256(b"a").hexdigest(), hashlib.sha256(b"b").hexdigest()]
    assert compute_merkle_root(hashes) == compute_merkle_root(hashes)


def test_compute_merkle_root_order_matters():
    """Swapping chunk order changes the root (order-preserving)."""
    from app.props.verifier import compute_merkle_root

    h1 = hashlib.sha256(b"first").hexdigest()
    h2 = hashlib.sha256(b"second").hexdigest()
    assert compute_merkle_root([h1, h2]) != compute_merkle_root([h2, h1])


def test_compute_merkle_root_single_chunk():
    """Single-chunk dataset: root = sha256(sha256(chunk_data))."""
    from app.props.verifier import compute_merkle_root

    chunk_data = b"only_chunk"
    chunk_hash = hashlib.sha256(chunk_data).hexdigest()
    expected_root = hashlib.sha256(bytes.fromhex(chunk_hash)).hexdigest()
    assert compute_merkle_root([chunk_hash]) == expected_root


def test_compute_merkle_root_empty_raises():
    from app.props.verifier import compute_merkle_root

    with pytest.raises(ValueError, match="non-empty"):
        compute_merkle_root([])


def test_validate_proof_structure_valid():
    from app.props.verifier import validate_proof_structure

    data_hash, proof = _build_valid_proof()
    assert validate_proof_structure(data_hash, proof) is None


def test_validate_proof_structure_bad_data_hash():
    from app.props.verifier import validate_proof_structure

    _, proof = _build_valid_proof()
    error = validate_proof_structure("not-a-hash", proof)
    assert error is not None
    assert "data_hash" in error


def test_validate_proof_structure_missing_field():
    from app.props.verifier import validate_proof_structure

    data_hash, proof = _build_valid_proof()
    del proof["chunk_count"]
    error = validate_proof_structure(data_hash, proof)
    assert error is not None
    assert "chunk_count" in error


def test_validate_proof_structure_wrong_algorithm():
    from app.props.verifier import validate_proof_structure

    data_hash, proof = _build_valid_proof()
    proof["algorithm"] = "md5"
    error = validate_proof_structure(data_hash, proof)
    assert error is not None
    assert "algorithm" in error


def test_validate_proof_structure_chunk_count_mismatch():
    from app.props.verifier import validate_proof_structure

    data_hash, proof = _build_valid_proof()
    proof["chunk_count"] = 999  # wrong
    error = validate_proof_structure(data_hash, proof)
    assert error is not None
    assert "chunk_count" in error


def test_validate_proof_structure_bad_chunk_hash():
    from app.props.verifier import validate_proof_structure

    data_hash, proof = _build_valid_proof()
    proof["chunk_hashes"][0] = "not-a-hex-string"
    error = validate_proof_structure(data_hash, proof)
    assert error is not None
    assert "chunk_hashes[0]" in error


def test_validate_proof_structure_empty_chunk_list():
    from app.props.verifier import validate_proof_structure

    data_hash, proof = _build_valid_proof()
    proof["chunk_hashes"] = []
    proof["chunk_count"] = 0
    error = validate_proof_structure(data_hash, proof)
    assert error is not None


# ---------------------------------------------------------------------------
# verify_data_authenticity — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_valid_proof_returns_verified_true():
    """Valid proof with matching root hash → verified=True, attestation set."""
    from app.props.verifier import verify_data_authenticity

    data_hash, proof = _build_valid_proof()

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = "mock-verification-quote"
        result = await verify_data_authenticity(data_hash, proof)

    assert result.verified is True
    assert result.data_hash == data_hash
    assert result.chunk_count == proof["chunk_count"]
    assert result.attestation == "mock-verification-quote"
    assert result.error is None


@pytest.mark.asyncio
async def test_verify_sign_result_called_with_correct_payload():
    """sign_result is called with {data_hash, verified, chunk_count, algorithm}."""
    from app.props.verifier import verify_data_authenticity

    data_hash, proof = _build_valid_proof([b"only_chunk"])

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = "quote"
        await verify_data_authenticity(data_hash, proof)

    sign_payload = mock_sign.call_args[0][0]
    assert sign_payload["data_hash"] == data_hash
    assert sign_payload["verified"] is True
    assert sign_payload["chunk_count"] == 1
    assert sign_payload["algorithm"] == "sha256"


@pytest.mark.asyncio
async def test_verify_single_chunk_proof():
    """Single-chunk dataset proof verifies correctly."""
    from app.props.verifier import verify_data_authenticity

    data_hash, proof = _build_valid_proof([b"the_entire_dataset"])

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = "quote"
        result = await verify_data_authenticity(data_hash, proof)

    assert result.verified is True
    assert result.chunk_count == 1


# ---------------------------------------------------------------------------
# verify_data_authenticity — failure paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_bad_data_hash_format():
    """Malformed data_hash string → verified=False without calling sign_result."""
    from app.props.verifier import verify_data_authenticity

    _, proof = _build_valid_proof()

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign:
        result = await verify_data_authenticity("INVALID", proof)

    assert result.verified is False
    assert result.error is not None
    mock_sign.assert_not_called()


@pytest.mark.asyncio
async def test_verify_root_hash_does_not_match_data_hash():
    """
    Tampered data_hash: advertised hash differs from proof root_hash.
    This is the most common attack — seller advertises one hash but submits
    a proof for a different dataset.
    """
    from app.props.verifier import verify_data_authenticity

    _, proof = _build_valid_proof()
    different_data_hash = hashlib.sha256(b"completely_different_dataset").hexdigest()

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign:
        result = await verify_data_authenticity(different_data_hash, proof)

    assert result.verified is False
    assert "root_hash" in result.error or "data_hash" in result.error
    mock_sign.assert_not_called()


@pytest.mark.asyncio
async def test_verify_tampered_chunk_hash():
    """
    Seller supplies correct root_hash but tampers one chunk hash.
    Merkle root recomputation will produce a different value → fail.
    """
    from app.props.verifier import verify_data_authenticity

    data_hash, proof = _build_valid_proof()
    # Replace first chunk hash with a random one (but keep root_hash unchanged)
    proof["chunk_hashes"][0] = hashlib.sha256(b"tampered").hexdigest()
    # root_hash stays as the original — mismatch will be detected

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign:
        result = await verify_data_authenticity(data_hash, proof)

    assert result.verified is False
    assert "Merkle root mismatch" in result.error
    mock_sign.assert_not_called()


@pytest.mark.asyncio
async def test_verify_wrong_chunk_count():
    """chunk_count field does not match len(chunk_hashes) → structural error."""
    from app.props.verifier import verify_data_authenticity

    data_hash, proof = _build_valid_proof()
    proof["chunk_count"] = 999

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign:
        result = await verify_data_authenticity(data_hash, proof)

    assert result.verified is False
    mock_sign.assert_not_called()


@pytest.mark.asyncio
async def test_verify_missing_seller_proof_fields():
    """Incomplete proof dict (missing chunk_hashes) → structural error."""
    from app.props.verifier import verify_data_authenticity

    data_hash = "a" * 64
    bad_proof = {"root_hash": data_hash, "algorithm": "sha256"}  # missing chunk_hashes, chunk_count

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign:
        result = await verify_data_authenticity(data_hash, bad_proof)

    assert result.verified is False
    mock_sign.assert_not_called()


@pytest.mark.asyncio
async def test_verify_unsupported_algorithm():
    from app.props.verifier import verify_data_authenticity

    data_hash, proof = _build_valid_proof()
    proof["algorithm"] = "md5"

    with patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign:
        result = await verify_data_authenticity(data_hash, proof)

    assert result.verified is False
    mock_sign.assert_not_called()


# ---------------------------------------------------------------------------
# Route-level: verification gate blocks negotiation on failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_verification_failure_returns_400():
    """
    When seller_proof is invalid, POST /api/deals/run returns HTTP 400
    and the negotiation loop is never entered.
    """
    import uuid
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, patch, MagicMock

    # Build a proof whose root_hash does NOT match data_hash
    data_hash, proof = _build_valid_proof()
    tampered_hash = hashlib.sha256(b"wrong_dataset").hexdigest()
    # proof.root_hash stays as original; data_hash is different → mismatch

    payload = {
        "buyer_budget": 1000,
        "buyer_requirements": "test",
        "data_description": "test",
        "data_hash": tampered_hash,     # does not match proof.root_hash
        "floor_price": 500,
        "seller_proof": proof,
    }

    # Patch DB so we don't need a real SQLite file in this test
    with patch("app.api.routes.db.create_deal", new_callable=AsyncMock), \
         patch("app.api.routes.db.update_deal", new_callable=AsyncMock), \
         patch("app.api.routes.db.get_deal", new_callable=AsyncMock), \
         patch("app.props.verifier.sign_result", new_callable=AsyncMock) as mock_sign, \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock) as mock_neg_sign:

        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/deals/run", json=payload)

    assert response.status_code == 400
    assert "verification failed" in response.json()["detail"].lower()
    mock_neg_sign.assert_not_called()  # negotiation never ran


@pytest.mark.asyncio
async def test_route_valid_proof_produces_both_attestations():
    """
    When seller_proof is valid, DealResult contains both
    data_verification_attestation (from Props) and attestation (from deal).
    """
    import json as _json
    from unittest.mock import AsyncMock, MagicMock, patch

    data_hash, proof = _build_valid_proof()

    payload = {
        "buyer_budget": 1000,
        "buyer_requirements": "test",
        "data_description": "test",
        "data_hash": data_hash,
        "floor_price": 500,
        "seller_proof": proof,
    }

    def _resp(text):
        m = MagicMock()
        m.content = [MagicMock(text=text)]
        return m

    async def seller_respond(*a, **kw):
        return _resp(_json.dumps({"action": "offer", "price": 700.0, "terms": {}, "reasoning": ""}))

    async def buyer_respond(*a, **kw):
        return _resp(_json.dumps({"action": "accept", "price": 700.0, "terms": {}, "reasoning": ""}))

    with patch("app.api.routes.db.create_deal", new_callable=AsyncMock), \
         patch("app.api.routes.db.update_deal", new_callable=AsyncMock), \
         patch("app.props.verifier.sign_result", new_callable=AsyncMock, return_value="props-quote-xyz"), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock, return_value="deal-quote-abc"):

        from app.agents.buyer import BuyerAgent
        from app.agents.seller import SellerAgent

        with patch.object(BuyerAgent, "evaluate_offer", new_callable=AsyncMock) as mock_buyer, \
             patch.object(SellerAgent, "make_offer", new_callable=AsyncMock) as mock_seller:

            mock_seller.return_value = {"action": "offer", "price": 700.0, "terms": {}, "reasoning": ""}
            mock_buyer.return_value = {"action": "accept", "price": 700.0, "terms": {}, "reasoning": ""}

            from app.main import app
            from fastapi.testclient import TestClient
            client = TestClient(app, raise_server_exceptions=True)
            response = client.post("/api/deals/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["agreed"] is True
    assert body["data_verification_attestation"] == "props-quote-xyz"
    assert body["attestation"] == "deal-quote-abc"
