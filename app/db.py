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


async def get_rooms_by_token(token: str) -> list[dict]:
    """
    Return all rooms where seller_token or buyer_token matches.
    Used by GET /api/room/history — typically returns 1 room per token since tokens are unique.
    Cap at 50, ordered by created_at desc.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT room_id, seller_name, buyer_name, status, deal_id, created_at,
                   seller_token, buyer_token
            FROM deal_rooms
            WHERE seller_token = ? OR buyer_token = ?
            ORDER BY created_at DESC LIMIT 50
            """,
            (token, token),
        ) as cursor:
            rows = await cursor.fetchall()

    result = []
    for row in rows:
        role = "seller" if row[6] == token else "buyer"
        result.append({
            "room_id": row[0],
            "seller_name": row[1],
            "buyer_name": row[2],
            "status": row[3],
            "deal_id": row[4],
            "created_at": row[5],
            "role": role,
        })
    return result


async def update_room_status(room_id: str, status: str) -> None:
    """Update room status — called by background task after negotiation finishes."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE deal_rooms SET status=?, updated_at=CURRENT_TIMESTAMP WHERE room_id=?",
            (status, room_id),
        )
        await db.commit()


async def start_room_deal(room_id: str, deal_id: str) -> bool:
    """
    Atomically transition room from 'confirmed' → 'running' and store deal_id.
    Returns True if this call made the transition (first caller wins).
    Returns False if room was already running (idempotent for concurrent calls).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE deal_rooms SET status='running', deal_id=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE room_id=? AND status='confirmed'",
            (deal_id, room_id),
        )
        await db.commit()
        return cursor.rowcount == 1


async def create_deal_rooms_table() -> None:
    """Create the deal_rooms table if it does not exist, and migrate Phase 2 columns."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS deal_rooms (
                room_id           TEXT PRIMARY KEY,
                seller_token      TEXT,
                buyer_token       TEXT,
                seller_name       TEXT,
                buyer_name        TEXT,
                seller_email      TEXT,
                seller_eth        TEXT,
                buyer_eth         TEXT,
                status            TEXT DEFAULT 'waiting',
                deal_id           TEXT,
                token_expires_at  INTEGER,
                deal_payload      TEXT,
                seller_confirmed  INTEGER DEFAULT 0,
                buyer_confirmed   INTEGER DEFAULT 0,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Safe migrations for Phase 1 installs that lack the Phase 2 columns.
        for col_sql in [
            "ALTER TABLE deal_rooms ADD COLUMN deal_payload TEXT",
            "ALTER TABLE deal_rooms ADD COLUMN seller_confirmed INTEGER DEFAULT 0",
            "ALTER TABLE deal_rooms ADD COLUMN buyer_confirmed INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass  # column already present
        await db.commit()


async def create_room(
    room_id: str,
    seller_token: str,
    seller_name: str,
    seller_email: str,
    seller_eth: str | None,
    token_expires_at: int,
) -> None:
    """Insert a new deal room with seller info."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO deal_rooms
              (room_id, seller_token, seller_name, seller_email, seller_eth, token_expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (room_id, seller_token, seller_name, seller_email, seller_eth, token_expires_at),
        )
        await db.commit()


async def get_room(room_id: str) -> dict | None:
    """Fetch a deal room by ID. Returns dict or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT room_id, seller_token, buyer_token, seller_name, buyer_name,
                   seller_email, seller_eth, buyer_eth, status, deal_id,
                   token_expires_at, deal_payload, seller_confirmed, buyer_confirmed,
                   created_at
            FROM deal_rooms WHERE room_id = ?
            """,
            (room_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "room_id": row[0],
        "seller_token": row[1],
        "buyer_token": row[2],
        "seller_name": row[3],
        "buyer_name": row[4],
        "seller_email": row[5],
        "seller_eth": row[6],
        "buyer_eth": row[7],
        "status": row[8],
        "deal_id": row[9],
        "token_expires_at": row[10],
        "deal_payload": row[11],
        "seller_confirmed": row[12],
        "buyer_confirmed": row[13],
        "created_at": row[14],
    }


async def update_room_buyer(
    room_id: str,
    buyer_token: str,
    buyer_name: str,
    buyer_eth: str | None,
) -> None:
    """Add buyer to a room and transition status to 'ready'."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE deal_rooms
            SET buyer_token = ?, buyer_name = ?, buyer_eth = ?,
                status = 'ready', updated_at = CURRENT_TIMESTAMP
            WHERE room_id = ?
            """,
            (buyer_token, buyer_name, buyer_eth, room_id),
        )
        await db.commit()


async def save_room_config(room_id: str, config: dict) -> None:
    """Persist deal configuration and transition status to 'configuring'."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE deal_rooms
            SET deal_payload = ?, status = 'configuring',
                seller_confirmed = 0, buyer_confirmed = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE room_id = ?
            """,
            (json.dumps(config), room_id),
        )
        await db.commit()


async def confirm_room_participant(room_id: str, role: str) -> tuple[bool, bool]:
    """
    Mark seller or buyer as confirmed.
    When both are confirmed, transitions status to 'confirmed'.
    Returns (seller_confirmed, buyer_confirmed) after the update.
    """
    col = "seller_confirmed" if role == "seller" else "buyer_confirmed"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE deal_rooms SET {col} = 1, updated_at = CURRENT_TIMESTAMP WHERE room_id = ?",
            (room_id,),
        )
        # Transition to 'confirmed' when both flags are set
        await db.execute(
            """
            UPDATE deal_rooms SET status = 'confirmed', updated_at = CURRENT_TIMESTAMP
            WHERE room_id = ? AND seller_confirmed = 1 AND buyer_confirmed = 1
            """,
            (room_id,),
        )
        await db.commit()

        async with db.execute(
            "SELECT seller_confirmed, buyer_confirmed FROM deal_rooms WHERE room_id = ?",
            (room_id,),
        ) as cursor:
            row = await cursor.fetchone()

    return bool(row[0]), bool(row[1])


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
