"""
Rate limiting tests for the Dev Credential vertical.

Covers:
  - POST /api/devcred/{id}/evaluate — 3 requests/hour/IP (slowapi), 429 on the 4th
  - POST /api/devcred/ingest        — 10 requests/hour/IP (slowapi), 429 on the 11th
  - Daily eval_counters hard stop (50/day across all callers) — 503 when exceeded
  - app/db.py eval_counters table: atomic increment + compensating decrement
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.rate_limit import limiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_db_path(tmp_path):
    """Redirect app.db.DB_PATH to a temp file so each test gets a clean DB."""
    import app.db as db_module
    original = db_module.DB_PATH
    db_module.DB_PATH = tmp_path / "test_dealproof.db"
    yield
    db_module.DB_PATH = original


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """slowapi's Limiter is a process-wide singleton — reset its storage between tests."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _fake_request(client_host: str = "10.0.0.1") -> Request:
    """Minimal Starlette Request satisfying slowapi's per-route rate-limit check."""
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/devcred/test/evaluate",
        "headers": [],
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    })


# ---------------------------------------------------------------------------
# 1. POST /ingest — 10/hour/IP
# ---------------------------------------------------------------------------

def test_ingest_rate_limited_at_10_per_hour(client):
    # Invalid repo format (no "/") fails fast with 400, before any GitHub call —
    # the rate limit still applies since slowapi checks before the route body runs.
    payload = {"github_token": "x", "repos": ["invalidrepo"], "credential_id": "cid"}

    for _ in range(10):
        resp = client.post("/api/devcred/ingest", json=payload)
        assert resp.status_code == 400

    resp = client.post("/api/devcred/ingest", json=payload)
    assert resp.status_code == 429
    assert "rate limit" in resp.json()["error"].lower()


# ---------------------------------------------------------------------------
# 2. POST /{id}/evaluate — 3/hour/IP
# ---------------------------------------------------------------------------

def test_evaluate_rate_limited_at_3_per_hour(client):
    # Unknown credential_id fails fast with 404 — same reasoning as above.
    for _ in range(3):
        resp = client.post("/api/devcred/unknown-id/evaluate")
        assert resp.status_code == 404

    resp = client.post("/api/devcred/unknown-id/evaluate")
    assert resp.status_code == 429
    assert "rate limit" in resp.json()["error"].lower()


# ---------------------------------------------------------------------------
# 3. Daily hard stop (50/day across all callers)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_daily_hard_stop_returns_503():
    """
    When the daily counter is already at/over the limit, the endpoint must
    return 503 before touching db.get_dev_credential or any paid API.
    """
    from app.devcred.routes import evaluate_credential

    with patch("app.devcred.routes.db") as mock_db:
        mock_db.increment_daily_eval_count = AsyncMock(return_value=51)
        mock_db.decrement_daily_eval_count = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await evaluate_credential(_fake_request(), "some-credential-id")

    assert exc_info.value.status_code == 503
    assert "daily" in exc_info.value.detail.lower()
    mock_db.decrement_daily_eval_count.assert_awaited_once()
    mock_db.get_dev_credential.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_daily_counter_not_exceeded_proceeds_to_lookup():
    """Below the daily limit, the pipeline proceeds past the counter check."""
    from app.devcred.routes import evaluate_credential

    with patch("app.devcred.routes.db") as mock_db:
        mock_db.increment_daily_eval_count = AsyncMock(return_value=1)
        mock_db.get_dev_credential = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await evaluate_credential(_fake_request(client_host="10.0.0.2"), "missing-id")

    # 404 from the credential lookup, not 503 — proves the daily gate let it through
    assert exc_info.value.status_code == 404
    mock_db.get_dev_credential.assert_awaited_once_with("missing-id")


# ---------------------------------------------------------------------------
# 4. eval_counters DB layer — atomic increment + compensating decrement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daily_eval_counter_increment_and_decrement():
    import app.db as db_module

    await db_module.create_eval_counter_table()
    day = "2026-07-12"

    assert await db_module.increment_daily_eval_count(day) == 1
    assert await db_module.increment_daily_eval_count(day) == 2

    # Compensating decrement (used when a call is rejected past the limit)
    await db_module.decrement_daily_eval_count(day)
    assert await db_module.increment_daily_eval_count(day) == 2

    # A different day gets its own independent counter
    assert await db_module.increment_daily_eval_count("2026-07-13") == 1
