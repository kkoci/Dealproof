"""
Hedera HCS deal outcome publishing — ETHGlobal M7.

Submits every deal outcome (agreed or failed) as a timestamped message to a
Hedera Consensus Service topic. The message is immutable and publicly verifiable
via the Mirror Node and HashScan.

Pattern mirrors app/contract/escrow.py and arc_anchor.py:
- Synchronous SDK call wrapped in asyncio.to_thread
- HederaNotConfigured raised when env vars absent — non-fatal to deal flow
- SDK: hiero_sdk_python — execute() returns receipt directly, no get_receipt() needed

Message format:
  { deal_id, outcome, attestation_hash, timestamp }
"""
import asyncio
import json
import logging
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class HederaNotConfigured(Exception):
    """Raised when HEDERA_ACCOUNT_ID / HEDERA_TOPIC_ID are not set."""


def _publish_sync(deal_id: str, outcome: str, attestation_hash: str) -> dict:
    if not settings.hedera_account_id:
        raise HederaNotConfigured("HEDERA_ACCOUNT_ID not configured")
    if not settings.hedera_topic_id:
        raise HederaNotConfigured("HEDERA_TOPIC_ID not configured")
    if not settings.hedera_private_key:
        raise HederaNotConfigured("HEDERA_PRIVATE_KEY not configured")

    from hiero_sdk_python import (
        AccountId,
        Client,
        PrivateKey,
        TopicId,
        TopicMessageSubmitTransaction,
    )

    operator_id = AccountId.from_string(settings.hedera_account_id)
    operator_key = PrivateKey.from_string(settings.hedera_private_key)

    client = Client()
    client.set_operator(operator_id, operator_key)

    message = json.dumps({
        "deal_id": deal_id,
        "outcome": outcome,
        "attestation_hash": attestation_hash,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    tx = (
        TopicMessageSubmitTransaction()
        .set_topic_id(TopicId.from_string(settings.hedera_topic_id))
        .set_message(message)
        .freeze_with(client)
        .sign(operator_key)
    )
    receipt = tx.execute(client)

    transaction_id = (
        str(tx.transaction_id)
        if hasattr(tx, "transaction_id")
        else f"{settings.hedera_account_id}@{deal_id[:8]}"
    )
    sequence_number = str(getattr(receipt, "topic_sequence_number", ""))

    logger.info(
        f"Hedera HCS: deal {deal_id} outcome '{outcome}' published — "
        f"tx={transaction_id}, seq={sequence_number}"
    )
    return {
        "transaction_id": transaction_id,
        "topic_id": settings.hedera_topic_id,
        "consensus_timestamp": sequence_number,
    }


async def publish_deal_outcome(deal_id: str, outcome: str, attestation_hash: str) -> dict:
    """
    Submit deal outcome to Hedera Consensus Service topic.

    Parameters
    ----------
    deal_id          : UUID string of the deal
    outcome          : "agreed" | "failed"
    attestation_hash : SHA-256(attestation_hex) — compact ref to TDX quote,
                       or "" when no attestation was produced (failed deals)

    Returns
    -------
    { transaction_id, topic_id, consensus_timestamp }

    Raises HederaNotConfigured when env vars are missing.
    """
    return await asyncio.to_thread(_publish_sync, deal_id, outcome, attestation_hash)
