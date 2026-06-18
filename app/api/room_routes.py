"""Deal Room endpoints — Phase 1+2 (product/deal-room).

Phase 1:
  POST /api/room/seller/register  — seller creates a room, gets a token + shareable URL
  POST /api/room/buyer/register   — buyer joins a waiting room, gets a token
  GET  /api/room/{room_id}/status — polls room status (public, no auth required)

Phase 2:
  PUT  /api/room/{room_id}/config   — seller saves deal configuration (X-Room-Token required)
  POST /api/room/{room_id}/confirm  — either party confirms the deal (X-Room-Token required)

Tokens are random 64-char hex strings stored in the deal_rooms table.
Auth uses the X-Room-Token header; the server resolves role from the token value.
"""
import json
import secrets
import time
import uuid

from fastapi import APIRouter, HTTPException, Header

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
from app.config import settings

router = APIRouter(prefix="/api/room", tags=["room"])

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
