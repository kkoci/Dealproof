"""
TEE integration tests — Phase 2.

Tests for app.tee.kms and app.tee.attestation.
All tappd HTTP calls are mocked with httpx response stubs so that:
  - Tests pass without docker-compose or a real Phala CVM running.
  - The mocks mirror the exact response shapes the real tappd returns.

tappd response formats
----------------------
DeriveKey:  {"key": "<hex string>", "certificate_chain": [...]}
TdxQuote:   {"quote": "<hex string>", "event_log": "..."}

The simulator and the real CVM return the same shape; only the values differ.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_httpx_client(json_response: dict):
    """Return an AsyncMock that behaves like an httpx.AsyncClient context manager."""
    mock_response = MagicMock()
    mock_response.json.return_value = json_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# kms.get_signing_key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_signing_key_returns_bytes():
    """get_signing_key() decodes the hex key from tappd and returns raw bytes."""
    from app.tee.kms import get_signing_key

    fake_key_hex = "deadbeef" * 8  # 32 bytes
    mock_ctx = _mock_httpx_client({"key": fake_key_hex, "certificate_chain": []})

    with patch("httpx.AsyncClient", return_value=mock_ctx):
        key = await get_signing_key()

    assert isinstance(key, bytes)
    assert key == bytes.fromhex(fake_key_hex)


@pytest.mark.asyncio
async def test_get_signing_key_strips_0x_prefix():
    """get_signing_key() handles tappd responses that include a 0x prefix on the key."""
    from app.tee.kms import get_signing_key

    fake_key_hex = "cafebabe" * 8
    mock_ctx = _mock_httpx_client({"key": "0x" + fake_key_hex, "certificate_chain": []})

    with patch("httpx.AsyncClient", return_value=mock_ctx):
        key = await get_signing_key()

    assert key == bytes.fromhex(fake_key_hex)


@pytest.mark.asyncio
async def test_get_signing_key_calls_correct_endpoint(tmp_path):
    """get_signing_key() posts to /prpc/Tappd.DeriveKey on the configured endpoint."""
    from app.tee.kms import get_signing_key

    fake_key_hex = "aabbccdd" * 8
    mock_ctx = _mock_httpx_client({"key": fake_key_hex, "certificate_chain": []})

    with patch("httpx.AsyncClient", return_value=mock_ctx):
        await get_signing_key()

    mock_client = mock_ctx.__aenter__.return_value
    call_args = mock_client.post.call_args
    assert "/prpc/Tappd.DeriveKey" in call_args[0][0]
    body = call_args[1]["json"]
    assert body["path"] == "dealproof/signing-key"
    assert body["subject"] == "dealproof-v1"


# ---------------------------------------------------------------------------
# attestation.sign_result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sign_result_returns_quote_string():
    """sign_result() returns the raw quote string from tappd (production mode)."""
    from app.tee.attestation import sign_result
    import app.tee.attestation as attestation_mod

    fake_quote = "0x" + "ab" * 128
    mock_ctx = _mock_httpx_client({"quote": fake_quote, "event_log": ""})

    terms = {"final_price": 750.0, "terms": {"access_scope": "full", "duration_days": 365}}

    with patch.object(attestation_mod.settings, "tee_mode", "production"), \
         patch("httpx.AsyncHTTPTransport"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        result = await sign_result(terms)

    assert result == fake_quote


@pytest.mark.asyncio
async def test_sign_result_report_data_is_64_bytes():
    """
    sign_result() builds report_data as 128 hex chars (64 bytes):
    SHA-256(canonical JSON) in the first 32 bytes, zero-padded to 64.
    """
    import hashlib, json
    from app.tee.attestation import sign_result
    import app.tee.attestation as attestation_mod

    fake_quote = "cc" * 128
    mock_ctx = _mock_httpx_client({"quote": fake_quote, "event_log": ""})

    terms = {"final_price": 500.0, "terms": {}}

    with patch.object(attestation_mod.settings, "tee_mode", "production"), \
         patch("httpx.AsyncHTTPTransport"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        await sign_result(terms)

    mock_client = mock_ctx.__aenter__.return_value
    call_args = mock_client.post.call_args
    report_data_hex = call_args[1]["json"]["report_data"]

    # Must be exactly 128 hex chars = 64 bytes
    assert len(report_data_hex) == 128

    # First 32 bytes must equal SHA-256 of the canonical JSON
    expected_digest = hashlib.sha256(
        json.dumps(terms, sort_keys=True).encode()
    ).hexdigest()
    assert report_data_hex[:64] == expected_digest

    # Last 32 bytes must be zero-padded
    assert report_data_hex[64:] == "00" * 32


@pytest.mark.asyncio
async def test_sign_result_calls_correct_endpoint():
    """sign_result() posts to /prpc/Tappd.TdxQuote (production mode)."""
    from app.tee.attestation import sign_result
    import app.tee.attestation as attestation_mod

    mock_ctx = _mock_httpx_client({"quote": "ff" * 128, "event_log": ""})

    with patch.object(attestation_mod.settings, "tee_mode", "production"), \
         patch("httpx.AsyncHTTPTransport"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        await sign_result({"final_price": 100.0, "terms": {}})

    mock_client = mock_ctx.__aenter__.return_value
    call_args = mock_client.post.call_args
    assert "/prpc/Tappd.TdxQuote" in call_args[0][0]


# ---------------------------------------------------------------------------
# End-to-end: negotiation produces attestation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_negotiation_agreed_has_attestation():
    """
    Full negotiation path: when a deal is agreed, result.attestation is a
    non-null string — the TDX quote from tappd.
    Both the Claude API and tappd are mocked.
    """
    import json as _json
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.buyer import BuyerAgent
    from app.agents.seller import SellerAgent
    from app.agents.negotiation import run_negotiation

    buyer = BuyerAgent(budget=1000.0, requirements="test data")
    seller = SellerAgent(floor_price=500.0, data_description="test dataset")

    def _resp(text):
        m = MagicMock()
        m.content = [MagicMock(text=text)]
        return m

    async def seller_respond(*a, **kw):
        return _resp(_json.dumps({"action": "offer", "price": 700.0, "terms": {}, "reasoning": ""}))

    async def buyer_respond(*a, **kw):
        return _resp(_json.dumps({"action": "accept", "price": 700.0, "terms": {}, "reasoning": ""}))

    mock_quote = "0x" + "dd" * 128

    # Patch the local binding in negotiation.py (where it is *used*),
    # not in app.tee.attestation (where it is *defined*).
    with patch.object(seller.client.messages, "create", side_effect=seller_respond), \
         patch.object(buyer.client.messages, "create", side_effect=buyer_respond), \
         patch("app.agents.negotiation.sign_result", new_callable=AsyncMock) as mock_sign:
        mock_sign.return_value = mock_quote
        result = await run_negotiation(buyer, seller, max_rounds=3)

    assert result.agreed is True
    assert result.attestation is not None
    assert result.attestation == mock_quote


@pytest.mark.asyncio
async def test_negotiation_failed_has_no_attestation():
    """When a deal fails (buyer rejects), attestation stays None."""
    import json as _json
    from app.agents.buyer import BuyerAgent
    from app.agents.seller import SellerAgent
    from app.agents.negotiation import run_negotiation

    buyer = BuyerAgent(budget=1000.0, requirements="test data")
    seller = SellerAgent(floor_price=500.0, data_description="test dataset")

    def _resp(text):
        m = MagicMock()
        m.content = [MagicMock(text=text)]
        return m

    async def seller_respond(*a, **kw):
        return _resp(_json.dumps({"action": "offer", "price": 9999.0, "terms": {}, "reasoning": ""}))

    async def buyer_respond(*a, **kw):
        return _resp(_json.dumps({"action": "reject", "price": 0.0, "terms": {}, "reasoning": ""}))

    with patch.object(seller.client.messages, "create", side_effect=seller_respond), \
         patch.object(buyer.client.messages, "create", side_effect=buyer_respond):
        result = await run_negotiation(buyer, seller, max_rounds=3)

    assert result.agreed is False
    assert result.attestation is None
