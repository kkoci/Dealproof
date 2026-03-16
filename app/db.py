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
