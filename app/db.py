"""
SQLite persistence layer — Phase 3.

Changes from Phase 2:
  - deals table gains a `verification` TEXT column storing the JSON of the
    VerificationResult returned by verify_data_authenticity().
  - init_db() runs an ALTER TABLE to add the column on existing Phase 2
    databases (SQLite silently succeeds; the except swallows the error if
    the column already exists).
  - create_deal() unchanged.
  - update_deal() gains optional `verification` parameter.
  - get_deal() returns the deserialized verification dict in the row.

Schema (v2 — Phase 3)
----------------------
deals
  id            TEXT  PRIMARY KEY   — UUID assigned at creation
  status        TEXT  NOT NULL      — pending | negotiating | agreed | failed | verification_failed
  payload       TEXT  NOT NULL      — JSON of original DealCreate fields
  result        TEXT  NULL          — JSON of DealResult (set after negotiation)
  verification  TEXT  NULL          — JSON of VerificationResult (set after Props check)
  created_at    TIMESTAMP           — auto-set by SQLite default
"""
import json
import aiosqlite
from pathlib import Path

DB_PATH = Path("dealproof.db")


async def init_db() -> None:
    """
    Create the deals table if it does not exist, and add the verification
    column to existing Phase 2 databases (safe no-op if already present).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS deals (
                id            TEXT PRIMARY KEY,
                status        TEXT NOT NULL,
                payload       TEXT NOT NULL,
                result        TEXT,
                verification  TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Safe migration: add column to existing Phase 2 DBs.
        # SQLite raises OperationalError "duplicate column name" if it exists.
        try:
            await db.execute("ALTER TABLE deals ADD COLUMN verification TEXT")
        except Exception:
            pass  # column already present — no action needed
        # ETHGlobal M8: ENS agent identity columns
        try:
            await db.execute("ALTER TABLE deals ADD COLUMN buyer_ens TEXT")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE deals ADD COLUMN seller_ens TEXT")
        except Exception:
            pass
        await db.commit()


async def create_deal(deal_id: str, payload: dict) -> None:
    """Insert a new deal in 'pending' status with its original payload."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO deals (id, status, payload) VALUES (?, ?, ?)",
            (deal_id, "pending", json.dumps(payload)),
        )
        await db.commit()


async def update_deal(
    deal_id: str,
    status: str,
    result: dict | None = None,
    verification: dict | None = None,
) -> None:
    """
    Update status, result, and/or verification for an existing deal.
    Passing None for result or verification leaves those columns unchanged
    only if called with result=None — the column is explicitly NULLed.
    To leave a column unchanged, read-modify-write is needed; for the current
    usage pattern (set once, never overwrite) this is not necessary.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE deals SET status = ?, result = ?, verification = ? WHERE id = ?",
            (
                status,
                json.dumps(result) if result is not None else None,
                json.dumps(verification) if verification is not None else None,
                deal_id,
            ),
        )
        await db.commit()


async def reset_stale_negotiations() -> int:
    """
    On startup, reset any deals stuck in 'negotiating' status to 'failed'.

    A deal can be left in 'negotiating' if the server crashed or was
    restarted mid-negotiation.  These deals will never progress on their own,
    so we mark them failed so callers get a clear status instead of
    'negotiating' forever.

    Returns the number of deals reset (0 is the normal case).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE deals SET status = 'failed' WHERE status = 'negotiating'"
        )
        await db.commit()
        count = cursor.rowcount
    if count:
        import logging
        logging.getLogger(__name__).warning(
            f"Startup recovery: reset {count} stale 'negotiating' deal(s) to 'failed'"
        )
    return count


async def claim_deal_for_negotiation(deal_id: str) -> bool:
    """
    Atomically transition a deal from 'pending' to 'negotiating'.

    Returns True if the transition succeeded (this caller now owns the deal).
    Returns False if the deal was already claimed by another caller — the
    caller should return HTTP 409 without running negotiation.

    This is the standard optimistic-lock pattern for single-writer DB
    access: one UPDATE with a WHERE clause on the old status, then check
    rowcount.  SQLite serialises writes, so no two callers can both see
    rowcount == 1 for the same deal_id.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE deals SET status = 'negotiating' WHERE id = ? AND status = 'pending'",
            (deal_id,),
        )
        await db.commit()
        return cursor.rowcount == 1


async def update_deal_ens(deal_id: str, buyer_ens: str | None, seller_ens: str | None) -> None:
    """Persist resolved ENS names for a deal's buyer and seller agents."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE deals SET buyer_ens = ?, seller_ens = ? WHERE id = ?",
            (buyer_ens, seller_ens, deal_id),
        )
        await db.commit()


async def get_all_deals_ens() -> list[dict]:
    """Return all deals with their ENS and address fields for GET /api/ens/agents."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, payload, buyer_ens, seller_ens FROM deals ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()

    result = []
    for row in rows:
        payload = json.loads(row[1]) if row[1] else {}
        result.append({
            "deal_id": row[0],
            "buyer_address": payload.get("buyer_address"),
            "buyer_ens": row[2],
            "seller_address": payload.get("seller_address"),
            "seller_ens": row[3],
        })
    return result


async def create_hedera_messages_table() -> None:
    """Create the hedera_messages table if it does not exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS hedera_messages (
                deal_id              TEXT PRIMARY KEY,
                transaction_id       TEXT NOT NULL,
                topic_id             TEXT NOT NULL,
                consensus_timestamp  TEXT,
                created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


async def save_hedera_message(
    deal_id: str,
    transaction_id: str,
    topic_id: str,
    consensus_timestamp: str,
) -> None:
    """Persist a Hedera HCS message record. INSERT OR REPLACE — idempotent."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO hedera_messages "
            "(deal_id, transaction_id, topic_id, consensus_timestamp) VALUES (?, ?, ?, ?)",
            (deal_id, transaction_id, topic_id, consensus_timestamp),
        )
        await db.commit()


async def get_hedera_message(deal_id: str) -> dict | None:
    """Fetch the Hedera HCS record for a deal. Returns dict or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT deal_id, transaction_id, topic_id, consensus_timestamp "
            "FROM hedera_messages WHERE deal_id = ?",
            (deal_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "deal_id": row[0],
        "transaction_id": row[1],
        "topic_id": row[2],
        "consensus_timestamp": row[3],
    }


async def create_arc_anchors_table() -> None:
    """Create the arc_anchors table if it does not exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS arc_anchors (
                deal_id    TEXT PRIMARY KEY,
                tx_hash    TEXT NOT NULL,
                record_id  TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


async def save_arc_anchor(deal_id: str, tx_hash: str, record_id: str) -> None:
    """Persist an Arc anchor record. INSERT OR REPLACE — idempotent."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO arc_anchors (deal_id, tx_hash, record_id) VALUES (?, ?, ?)",
            (deal_id, tx_hash, record_id),
        )
        await db.commit()


async def get_arc_anchor(deal_id: str) -> dict | None:
    """Fetch the Arc anchor record for a deal. Returns {deal_id, tx_hash, record_id} or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT deal_id, tx_hash, record_id FROM arc_anchors WHERE deal_id = ?",
            (deal_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {"deal_id": row[0], "tx_hash": row[1], "record_id": row[2]}


async def create_transcript_corpora_table() -> None:
    """Create the transcript_corpora table if it does not exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_corpora (
                corpus_id          TEXT PRIMARY KEY,
                conversations_json TEXT NOT NULL,
                corpus_root        TEXT NOT NULL,
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


async def save_corpus(corpus_id: str, conversations: list[dict], corpus_root: str) -> None:
    """Persist a corpus. INSERT OR REPLACE — idempotent re-ingestion of the same corpus_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO transcript_corpora (corpus_id, conversations_json, corpus_root) VALUES (?, ?, ?)",
            (corpus_id, json.dumps(conversations), corpus_root),
        )
        await db.commit()


async def get_corpus_by_root(corpus_root: str) -> dict | None:
    """
    Fetch a corpus by its Merkle root hash.
    Used by the credential endpoint to look up conversations by data_hash.
    Returns {corpus_id, conversations (list), corpus_root} or None.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT corpus_id, conversations_json, corpus_root FROM transcript_corpora WHERE corpus_root = ?",
            (corpus_root,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "corpus_id": row[0],
        "conversations": json.loads(row[1]),
        "corpus_root": row[2],
    }


async def create_compliance_audits_table() -> None:
    """Create the compliance_audits table if it does not exist (SOC 2 vertical)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS compliance_audits (
                audit_id           TEXT PRIMARY KEY,
                org_name           TEXT NOT NULL,
                config_corpus_root TEXT NOT NULL,
                config_hashes_json TEXT NOT NULL,
                configs_json       TEXT,
                controls_json      TEXT,
                credential_json    TEXT,
                quality_hash       TEXT,
                tee_quote          TEXT,
                status             TEXT DEFAULT 'pending',
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Safe migration for existing Phase S1 databases
        try:
            await db.execute("ALTER TABLE compliance_audits ADD COLUMN configs_json TEXT")
        except Exception:
            pass
        await db.commit()


async def create_audit(
    audit_id: str,
    org_name: str,
    config_corpus_root: str,
    config_hashes_json: str,
    configs_json: str = "",
) -> None:
    """Insert a new compliance audit row in 'pending' status."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO compliance_audits
            (audit_id, org_name, config_corpus_root, config_hashes_json, configs_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (audit_id, org_name, config_corpus_root, config_hashes_json, configs_json),
        )
        await db.commit()


async def update_audit(
    audit_id: str,
    status: str,
    controls_json: str | None = None,
    credential_json: str | None = None,
    quality_hash: str | None = None,
    tee_quote: str | None = None,
) -> None:
    """Update a compliance audit row — only touches non-None fields."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE compliance_audits
            SET status = ?,
                controls_json   = COALESCE(?, controls_json),
                credential_json = COALESCE(?, credential_json),
                quality_hash    = COALESCE(?, quality_hash),
                tee_quote       = COALESCE(?, tee_quote)
            WHERE audit_id = ?
            """,
            (status, controls_json, credential_json, quality_hash, tee_quote, audit_id),
        )
        await db.commit()


async def get_audit(audit_id: str) -> dict | None:
    """Fetch a compliance audit row by ID. Returns dict or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT audit_id, org_name, config_corpus_root, config_hashes_json,
                   configs_json, controls_json, credential_json, quality_hash,
                   tee_quote, status, created_at
            FROM compliance_audits WHERE audit_id = ?
            """,
            (audit_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "audit_id":           row[0],
        "org_name":           row[1],
        "config_corpus_root": row[2],
        "config_hashes":      json.loads(row[3]) if row[3] else [],
        "configs":            json.loads(row[4]) if row[4] else [],
        "controls":           json.loads(row[5]) if row[5] else None,
        "credential":         json.loads(row[6]) if row[6] else None,
        "quality_hash":       row[7],
        "tee_quote":          row[8],
        "status":             row[9],
        "created_at":         row[10],
    }


async def get_deal(deal_id: str) -> dict | None:
    """
    Fetch a deal row by ID.

    Returns a dict with keys:
      id, status, payload (dict), result (dict|None), verification (dict|None).
    Returns None if the deal does not exist.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, status, payload, result, verification FROM deals WHERE id = ?",
            (deal_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "status": row[1],
        "payload": json.loads(row[2]),
        "result": json.loads(row[3]) if row[3] is not None else None,
        "verification": json.loads(row[4]) if row[4] is not None else None,
    }
