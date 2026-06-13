"""
Tests for ETHGlobal NYC TinyCloud integration — Milestones 1–4.

Covers:
  - transcript_hasher (pure unit)
  - DataCredentialAgent (mock AsyncAnthropic)
  - POST /api/transcripts/ingest direct mode (TestClient + temp DB)
  - POST /api/deals/{id}/credential (TestClient + temp DB + mocks)
"""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


SAMPLE_CONVERSATIONS = [
    {
        "id": "conv-1",
        "title": "Q4 Planning",
        "source": "fireflies",
        "started_at": "2026-06-01T10:00:00Z",
        "summary": "Team agreed to ship by end of June. Three action items assigned.",
        "sentences": [],
    },
    {
        "id": "conv-2",
        "title": "Architecture Review",
        "source": "google_meet",
        "started_at": "2026-06-05T14:00:00Z",
        "summary": None,
        "sentences": [
            {"index": 0, "speaker_id": "alice", "speaker_name": "Alice",
             "text": "We should use TEE for this.", "start_time": 0.0, "end_time": 3.0, "language": "en"},
            {"index": 1, "speaker_id": "bob", "speaker_name": "Bob",
             "text": "Agreed, Phala is the right choice.", "start_time": 3.5, "end_time": 6.0, "language": "en"},
        ],
    },
]

ASSESSMENT_RESPONSE = {
    "decision_velocity": 2,
    "collaboration_balance": 0.75,
    "commitment_count": 3,
    "conflict_resolution": "constructive",
    "technical_depth": "deep",
    "execution_signal": "strong",
    "summary": "Fast-moving team with balanced collaboration and clear technical direction.",
}


# ---------------------------------------------------------------------------
# Pure unit — transcript hasher
# ---------------------------------------------------------------------------

def test_transcript_hasher_produces_deterministic_root():
    from app.props.transcript_hasher import hash_transcript, compute_corpus_root

    sentences = SAMPLE_CONVERSATIONS[1]["sentences"]
    h_forward = hash_transcript(sentences)
    h_reversed = hash_transcript(list(reversed(sentences)))
    assert h_forward == h_reversed                    # order-independent
    assert len(h_forward) == 64

    root_a = compute_corpus_root([h_forward, "a" * 64])
    root_b = compute_corpus_root([h_forward, "a" * 64])
    assert root_a == root_b                           # deterministic
    assert len(root_a) == 64


# ---------------------------------------------------------------------------
# Pure unit — DataCredentialAgent empty corpus
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_data_credential_agent_handles_empty_corpus():
    from app.agents.data_credential import DataCredentialAgent

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        agent = DataCredentialAgent()
        result = await agent.assess([])

    assert result == {"error": "assessment_failed"}
    mock_client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# Agent unit — mock AsyncAnthropic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_data_credential_agent_returns_valid_json():
    from app.agents.data_credential import DataCredentialAgent

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(json.dumps(ASSESSMENT_RESPONSE))
        )
        agent = DataCredentialAgent()
        result = await agent.assess(SAMPLE_CONVERSATIONS)

    assert result["decision_velocity"] == 2
    assert result["execution_signal"] == "strong"
    assert "summary" in result
    mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_data_credential_agent_uses_summary_when_available():
    from app.agents.data_credential import DataCredentialAgent

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=_mock_response(json.dumps(ASSESSMENT_RESPONSE))
        )
        agent = DataCredentialAgent()
        await agent.assess(SAMPLE_CONVERSATIONS)

    call_args = mock_client.messages.create.call_args
    prompt_content = call_args[1]["messages"][0]["content"]
    # conv-1 has a summary — it must appear in the prompt
    assert "Team agreed to ship by end of June" in prompt_content
    # raw sentence fields must NOT appear (summary was preferred)
    assert "speaker_id" not in prompt_content


# ---------------------------------------------------------------------------
# Endpoint integration — ingest direct mode
# ---------------------------------------------------------------------------

def test_ingest_endpoint_direct_mode_returns_seller_proof():
    import pathlib, tempfile
    import app.db as db_module
    from fastapi.testclient import TestClient

    orig = db_module.DB_PATH
    payload = {
        "corpus_id": "test-corpus-1",
        "mode": "direct",
        "conversations": SAMPLE_CONVERSATIONS,
    }

    with tempfile.TemporaryDirectory() as tmp:
        db_module.DB_PATH = pathlib.Path(tmp) / "test.db"
        from app.main import app as fastapi_app
        with TestClient(fastapi_app) as client:
            response = client.post("/api/transcripts/ingest", json=payload)
        db_module.DB_PATH = orig

    assert response.status_code == 200
    body = response.json()
    assert body["corpus_id"] == "test-corpus-1"
    assert body["conversation_count"] == 2
    assert len(body["corpus_root"]) == 64
    assert body["seller_proof"]["algorithm"] == "sha256"
    assert body["seller_proof"]["chunk_count"] == 2
    assert body["seller_proof"]["root_hash"] == body["corpus_root"]
    assert body["summaries_available"] == 1  # only conv-1 has a summary


# ---------------------------------------------------------------------------
# Endpoint integration — credential endpoint
# ---------------------------------------------------------------------------

def test_credential_endpoint_requires_agreed_deal():
    import pathlib, tempfile, asyncio
    import app.db as db_module
    from fastapi.testclient import TestClient

    orig = db_module.DB_PATH

    async def _seed(path):
        db_module.DB_PATH = path
        await db_module.init_db()
        await db_module.create_transcript_corpora_table()
        await db_module.create_deal("deal-pending-1", {
            "buyer_budget": 1000.0, "buyer_requirements": "test",
            "data_description": "test", "data_hash": "a" * 64, "floor_price": 600.0,
        })

    with tempfile.TemporaryDirectory() as tmp:
        db_path = pathlib.Path(tmp) / "test.db"
        asyncio.run(_seed(db_path))

        from app.main import app as fastapi_app
        with TestClient(fastapi_app) as client:
            response = client.post("/api/deals/deal-pending-1/credential")

        db_module.DB_PATH = orig

    assert response.status_code == 409
    assert "not agreed" in response.json()["detail"]


def test_credential_endpoint_returns_attestation():
    import pathlib, tempfile, asyncio
    import app.db as db_module
    from fastapi.testclient import TestClient
    from unittest.mock import patch as _patch, AsyncMock as _AM

    orig = db_module.DB_PATH
    corpus_root = "b" * 64

    async def _seed(path):
        db_module.DB_PATH = path
        await db_module.init_db()
        await db_module.create_transcript_corpora_table()
        await db_module.create_deal("deal-cred-1", {
            "buyer_budget": 1000.0, "buyer_requirements": "test",
            "data_description": "test", "data_hash": corpus_root, "floor_price": 600.0,
        })
        await db_module.update_deal(
            "deal-cred-1", "agreed",
            result={"agreed": True, "final_price": 800.0},
        )
        await db_module.save_corpus("corpus-1", SAMPLE_CONVERSATIONS, corpus_root)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = pathlib.Path(tmp) / "test.db"
        asyncio.run(_seed(db_path))

        from app.main import app as fastapi_app
        with TestClient(fastapi_app) as client:
            with _patch("app.agents.data_credential.DataCredentialAgent.assess",
                        new_callable=_AM, return_value=ASSESSMENT_RESPONSE), \
                 _patch("app.api.routes.sign_result",
                        new_callable=_AM, return_value="mock-tee-quote"):
                response = client.post("/api/deals/deal-cred-1/credential")

        db_module.DB_PATH = orig

    assert response.status_code == 200
    body = response.json()
    assert body["deal_id"] == "deal-cred-1"
    assert body["attestation"] == "mock-tee-quote"
    assert body["verifiable"] is True
    assert body["credential"]["credential_type"] == "TeamDynamicsCredential"
    assert body["credential"]["corpus_root"] == corpus_root
    assert body["credential"]["subject"]["execution_signal"] == "strong"
