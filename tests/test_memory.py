"""
Tests for app/memory/client.py — the Python client for the memory sidecar.

All tests mock httpx so no real sidecar needs to be running.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(json_data: dict, status_code: int = 200):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_memories_ok():
    from app.memory.client import add_memories

    mock_resp = _mock_response({"stored": 2, "ids": ["id-1", "id-2"]})

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_client

        result = await add_memories(
            "buyer",
            [{"role": "user", "content": "Deal agreed at 800"}],
            user_id="deal-123",
        )

    assert result["stored"] == 2
    assert result["ids"] == ["id-1", "id-2"]
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[0][0] == "/memory/buyer/add"


@pytest.mark.asyncio
async def test_search_memories_ok():
    from app.memory.client import search_memories

    mock_resp = _mock_response({
        "results": [
            {"id": "r1", "content": "Buyer accepted 750 last deal", "score": 0.9},
            {"id": "r2", "content": "Seller floor was 600", "score": 0.8},
        ]
    })

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_client

        results = await search_memories("buyer", "pricing patterns for image datasets")

    assert len(results) == 2
    assert results[0]["content"] == "Buyer accepted 750 last deal"


@pytest.mark.asyncio
async def test_get_memory_hash_ok():
    from app.memory.client import get_memory_hash

    fake_hash = "a" * 64
    mock_resp = _mock_response({"hash": fake_hash, "count": 5, "timestamp": 1700000000000})

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_client

        result = await get_memory_hash("buyer")

    assert result["hash"] == fake_hash
    assert len(result["hash"]) == 64
    assert result["count"] == 5


@pytest.mark.asyncio
async def test_memory_failure_does_not_block_deal():
    """
    When the memory sidecar is unreachable, the try/except in routes._negotiate_deal
    catches the error and the deal proceeds with memory_hash="".
    """
    import hashlib

    data_hash = "d" * 64
    payload = {
        "buyer_budget": 1000.0,
        "buyer_requirements": "test dataset",
        "data_description": "test data",
        "data_hash": data_hash,
        "floor_price": 600.0,
    }

    def agent_response(action, price):
        return {
            "action": action,
            "price": price,
            "terms": {"access_scope": "full", "duration_days": 30},
            "reasoning": "test",
        }

    import app.db as db_module
    import tempfile, pathlib
    orig = db_module.DB_PATH

    with tempfile.TemporaryDirectory() as tmp:
        db_module.DB_PATH = pathlib.Path(tmp) / "test.db"

        from fastapi.testclient import TestClient
        from app.main import app as fastapi_app
        from unittest.mock import patch as _patch, AsyncMock as _AM

        with TestClient(fastapi_app, raise_server_exceptions=True) as client:
            with _patch("app.api.routes.search_memories", side_effect=httpx.ConnectError("sidecar down")), \
                 _patch("app.api.routes.add_memories", side_effect=httpx.ConnectError("sidecar down")), \
                 _patch("app.api.routes.get_memory_hash", side_effect=httpx.ConnectError("sidecar down")), \
                 _patch("app.agents.negotiation.sign_result", new_callable=_AM, return_value="deal-quote"), \
                 _patch("app.agents.buyer.BuyerAgent.evaluate_offer", new_callable=_AM, return_value=agent_response("accept", 800.0)), \
                 _patch("app.agents.seller.SellerAgent.make_offer", new_callable=_AM, return_value=agent_response("offer", 800.0)):

                response = client.post("/api/deals/run", json=payload)

        db_module.DB_PATH = orig

    assert response.status_code == 200
    body = response.json()
    assert body["agreed"] is True
    assert body["memory_hash"] is None
    assert body["memory_attested"] is False
