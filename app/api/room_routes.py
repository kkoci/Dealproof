"""Deal Room endpoints — Phase 1+2+3+5 (product/deal-room).

Phase 1:
  POST /api/room/seller/register  — seller creates a room, gets a token + shareable URL
  POST /api/room/buyer/register   — buyer joins a waiting room, gets a token
  GET  /api/room/{room_id}/status — polls room status (public, no auth required)

Phase 2:
  PUT  /api/room/{room_id}/config   — seller saves deal configuration (X-Room-Token required)
  POST /api/room/{room_id}/confirm  — either party confirms the deal (X-Room-Token required)

Phase 3:
  POST /api/room/{room_id}/start    — fires negotiation as a background task; idempotent

Phase 5:
  POST /api/room/{room_id}/dataset  — seller uploads CSV/JSON; returns Merkle root + quality preview

Tokens are random 64-char hex strings stored in the deal_rooms table.
Auth uses the X-Room-Token header; the server resolves role from the token value.
"""
import csv
import hashlib
import io
import json
import logging
import secrets
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Header, UploadFile

from app.api.room_schemas import (
    BuyerJoinResponse,
    BuyerRegisterRequest,
    ConfirmResponse,
    DealConfigRequest,
    RoomCreateResponse,
    RoomStatusResponse,
    SellerRegisterRequest,
)
import app.db as db
from app.api.schemas import DealCreate, DataQualityMetrics
from app.api.routes import _negotiate_deal
from app.props.verifier import compute_merkle_root
from app.config import settings

router = APIRouter(prefix="/api/room", tags=["room"])
logger = logging.getLogger(__name__)

TOKEN_TTL = 7200  # 2 hours in seconds


def _frontend_url() -> str:
    return getattr(settings, "frontend_url", "http://localhost:5173")


async def _resolve_role(room: dict, token: str) -> str:
    """Return 'seller' or 'buyer' for a given token, or raise 403."""
    if room["seller_token"] == token:
        return "seller"
    if room["buyer_token"] == token:
        return "buyer"
    raise HTTPException(status_code=403, detail="Invalid token")


# ── Phase 1 endpoints ──────────────────────────────────────────────────────

@router.post("/seller/register", response_model=RoomCreateResponse)
async def seller_register(body: SellerRegisterRequest) -> RoomCreateResponse:
    """Create a new deal room. Returns the seller's session token and a shareable room URL."""
    room_id = str(uuid.uuid4())
    seller_token = secrets.token_hex(32)
    expires_at = int(time.time()) + TOKEN_TTL

    await db.create_room(
        room_id=room_id,
        seller_token=seller_token,
        seller_name=body.name,
        seller_email=body.email,
        seller_eth=body.eth_address,
        token_expires_at=expires_at,
    )

    return RoomCreateResponse(
        room_id=room_id,
        room_url=f"{_frontend_url()}/room/{room_id}",
        seller_token=seller_token,
        expires_at=expires_at,
    )


@router.post("/buyer/register", response_model=BuyerJoinResponse)
async def buyer_register(body: BuyerRegisterRequest) -> BuyerJoinResponse:
    """Join an existing deal room as buyer. Returns the buyer's session token."""
    room = await db.get_room(body.room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room["status"] != "waiting":
        raise HTTPException(status_code=409, detail="Room already has a buyer")

    buyer_token = secrets.token_hex(32)
    expires_at = int(time.time()) + TOKEN_TTL

    await db.update_room_buyer(
        room_id=body.room_id,
        buyer_token=buyer_token,
        buyer_name=body.name,
        buyer_eth=body.eth_address,
    )

    return BuyerJoinResponse(
        buyer_token=buyer_token,
        room_id=body.room_id,
        seller_name=room["seller_name"],
        expires_at=expires_at,
    )


@router.get("/{room_id}/status", response_model=RoomStatusResponse)
async def get_room_status(room_id: str) -> RoomStatusResponse:
    """Return current room status. Polled every 3 s by the UI."""
    room = await db.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    raw_payload = room.get("deal_payload")
    payload_dict = json.loads(raw_payload) if raw_payload else None

    # Strip floor_price — it must never reach the buyer via this public endpoint.
    # The seller's local form state retains it; only the backend uses it for DealCreate.
    if payload_dict:
        payload_dict = {k: v for k, v in payload_dict.items() if k != "floor_price"}

    return RoomStatusResponse(
        room_id=room["room_id"],
        status=room["status"],
        seller_name=room["seller_name"],
        buyer_name=room["buyer_name"],
        seller_eth=room["seller_eth"],
        buyer_eth=room["buyer_eth"],
        deal_id=room["deal_id"],
        created_at=room["created_at"],
        deal_payload=payload_dict,
        seller_confirmed=bool(room.get("seller_confirmed", 0)),
        buyer_confirmed=bool(room.get("buyer_confirmed", 0)),
    )


# ── Phase 2 endpoints ──────────────────────────────────────────────────────

@router.put("/{room_id}/config")
async def save_config(
    room_id: str,
    body: DealConfigRequest,
    x_room_token: str = Header(alias="x-room-token"),
) -> dict:
    """Seller saves deal configuration. Transitions room status to 'configuring'."""
    room = await db.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room["seller_token"] != x_room_token:
        raise HTTPException(status_code=403, detail="Seller token required")
    if room["status"] not in ("ready", "configuring"):
        raise HTTPException(status_code=409, detail=f"Cannot configure room in status '{room['status']}'")

    await db.save_room_config(room_id, body.model_dump())
    return {"saved": True, "status": "configuring"}


@router.post("/{room_id}/confirm", response_model=ConfirmResponse)
async def confirm_deal(
    room_id: str,
    x_room_token: str = Header(alias="x-room-token"),
) -> ConfirmResponse:
    """Either party confirms the deal. When both confirm, status → 'confirmed'."""
    room = await db.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if not room.get("deal_payload"):
        raise HTTPException(status_code=409, detail="Seller must save configuration before confirming")
    if room["status"] not in ("configuring", "confirmed"):
        raise HTTPException(status_code=409, detail=f"Cannot confirm room in status '{room['status']}'")

    role = await _resolve_role(room, x_room_token)
    seller_confirmed, buyer_confirmed = await db.confirm_room_participant(room_id, role)

    both = seller_confirmed and buyer_confirmed
    new_status = "confirmed" if both else room["status"]

    return ConfirmResponse(
        role_confirmed=role,
        seller_confirmed=seller_confirmed,
        buyer_confirmed=buyer_confirmed,
        status=new_status,
    )


# ── Phase 5 helpers + endpoint ────────────────────────────────────────────

_MAX_FILE_BYTES = 50 * 1024 * 1024   # 50 MB
_CHUNK_BYTES    = 1024 * 1024         # 1 MB per Merkle chunk
_MAX_PREVIEW_ROWS = 10_000


def _chunk_and_hash(data: bytes) -> tuple[list[str], str]:
    """Split data into 1 MB chunks, SHA-256 each, compute flat Merkle root."""
    payload = data or b"\x00"
    pieces = [payload[i : i + _CHUNK_BYTES] for i in range(0, len(payload), _CHUNK_BYTES)]
    chunk_hashes = [hashlib.sha256(p).hexdigest() for p in pieces]
    return chunk_hashes, compute_merkle_root(chunk_hashes)


def _quality_preview(data: bytes, filename: str) -> dict:
    """Parse CSV / JSON up to _MAX_PREVIEW_ROWS rows; return basic quality metrics."""
    fname = filename.lower()
    rows: list[dict] = []
    columns: list[str] = []

    try:
        text = data.decode("utf-8", errors="replace")
        if fname.endswith(".csv"):
            reader = csv.DictReader(io.StringIO(text))
            columns = list(reader.fieldnames or [])
            for i, row in enumerate(reader):
                if i >= _MAX_PREVIEW_ROWS:
                    break
                rows.append(dict(row))
        elif fname.endswith(".json"):
            parsed = json.loads(text)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                columns = list(parsed[0].keys())
                rows = parsed[:_MAX_PREVIEW_ROWS]
        elif fname.endswith(".jsonl"):
            for i, line in enumerate(text.splitlines()):
                if i >= _MAX_PREVIEW_ROWS or not line.strip():
                    break
                obj = json.loads(line)
                if isinstance(obj, dict):
                    if not columns:
                        columns = list(obj.keys())
                    rows.append(obj)
    except Exception as exc:
        return {"parse_error": str(exc), "row_count": 0, "column_names": [], "null_rates": {}}

    if not rows or not columns:
        return {"row_count": len(rows), "column_names": columns, "null_rates": {},
                "completeness_score": 1.0, "quality_issues": [], "overall_quality": "high"}

    row_count = len(rows)
    null_rates: dict[str, float] = {}
    for col in columns:
        n = sum(1 for r in rows if r.get(col) is None or r.get(col) == "")
        null_rates[col] = round(n / row_count, 4)

    completeness = 1.0 - (sum(null_rates.values()) / len(null_rates)) if null_rates else 1.0
    quality_issues = [
        f"{rate * 100:.1f}% null rate in '{col}'"
        for col, rate in sorted(null_rates.items(), key=lambda x: -x[1])
        if rate > 0.05
    ][:10]
    overall = "high" if completeness >= 0.9 else "medium" if completeness >= 0.7 else "low"

    return {
        "row_count": row_count,
        "column_names": columns,
        "null_rates": null_rates,
        "completeness_score": round(completeness, 4),
        "quality_issues": quality_issues,
        "overall_quality": overall,
        "preview_capped": len(rows) == _MAX_PREVIEW_ROWS,
    }


@router.post("/{room_id}/dataset")
async def upload_dataset(
    room_id: str,
    file: UploadFile = File(...),
    x_room_token: str = Header(alias="x-room-token"),
) -> dict:
    """
    Seller uploads a CSV or JSON dataset.
    Returns corpus_root (Merkle root = data_hash) + seller_proof + quality preview.
    """
    room = await db.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if room["seller_token"] != x_room_token:
        raise HTTPException(status_code=403, detail="Seller token required")
    if room["status"] not in ("waiting", "ready", "configuring"):
        raise HTTPException(status_code=409, detail=f"Cannot upload in room status '{room['status']}'")

    data = await file.read()
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {_MAX_FILE_BYTES // 1024 // 1024} MB)")

    fname = file.filename or "dataset"
    if not any(fname.lower().endswith(ext) for ext in (".csv", ".json", ".jsonl")):
        raise HTTPException(status_code=415, detail="Unsupported file type. Allowed: .csv, .json, .jsonl")

    chunk_hashes, corpus_root = _chunk_and_hash(data)
    seller_proof = {
        "root_hash": corpus_root,
        "chunk_hashes": chunk_hashes,
        "chunk_count": len(chunk_hashes),
        "algorithm": "sha256",
    }
    quality_preview = _quality_preview(data, fname)

    logger.info(f"Room {room_id}: dataset uploaded — {len(data)} bytes, {len(chunk_hashes)} chunks, root {corpus_root[:16]}…")

    return {
        "corpus_root": corpus_root,
        "seller_proof": seller_proof,
        "file_size_bytes": len(data),
        "chunk_count": len(chunk_hashes),
        "filename": fname,
        "quality_preview": quality_preview,
    }


# ── Phase 3 endpoint ───────────────────────────────────────────────────────

async def _negotiate_and_complete_room(room_id: str, deal_id: str, deal_create: DealCreate) -> None:
    """Background task: run negotiation, then mark room complete or failed."""
    try:
        await _negotiate_deal(deal_id, deal_create)
        row = await db.get_deal(deal_id)
        final = "complete" if row and row["status"] == "agreed" else "failed"
        await db.update_room_status(room_id, final)
    except Exception as exc:
        logger.error(f"Room {room_id} background negotiation error: {exc}")
        await db.update_room_status(room_id, "failed")


@router.post("/{room_id}/start")
async def start_deal(
    room_id: str,
    background_tasks: BackgroundTasks,
    x_room_token: str = Header(alias="x-room-token"),
) -> dict:
    """
    Fire the negotiation as a background task. Idempotent — if the room is
    already running, returns the existing deal_id without starting a second deal.
    """
    room = await db.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    # Idempotent: already running
    if room["status"] == "running" and room["deal_id"]:
        return {"deal_id": room["deal_id"], "status": "running"}

    if room["status"] != "confirmed":
        raise HTTPException(status_code=409, detail=f"Cannot start deal in status '{room['status']}'")

    await _resolve_role(room, x_room_token)  # validates token

    raw = json.loads(room["deal_payload"])
    deal_id = str(uuid.uuid4())

    # Phase 5: use corpus_root from uploaded dataset if present; fall back to description hash
    data_hash = raw.get("corpus_root") or hashlib.sha256(raw["data_description"].encode()).hexdigest()

    # Phase 5: include seller_proof for Props verification if dataset was uploaded
    seller_proof = raw.get("seller_proof") or None

    # Phase 5: reconstruct DataQualityMetrics if quality_metrics present in payload
    quality_metrics = None
    qm_raw = raw.get("quality_metrics")
    if qm_raw and isinstance(qm_raw, dict):
        try:
            quality_metrics = DataQualityMetrics(**qm_raw)
        except Exception:
            pass  # non-fatal — proceed without quality context

    deal_create = DealCreate(
        data_description=raw["data_description"],
        buyer_requirements=raw.get("buyer_requirements", ""),
        floor_price=float(raw["floor_price"]),
        buyer_budget=float(raw["buyer_budget"]),
        data_hash=data_hash,
        seller_proof=seller_proof,
        quality_metrics=quality_metrics,
    )

    await db.create_deal(deal_id, deal_create.model_dump())

    # Atomic claim — first caller wins, second gets the already-claimed deal_id
    claimed = await db.start_room_deal(room_id, deal_id)
    if not claimed:
        room = await db.get_room(room_id)
        return {"deal_id": room["deal_id"], "status": "running"}

    background_tasks.add_task(_negotiate_and_complete_room, room_id, deal_id, deal_create)
    logger.info(f"Room {room_id}: negotiation started in background (deal {deal_id})")

    return {"deal_id": deal_id, "status": "running"}
