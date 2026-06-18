"""Deal Room endpoints — Phase 1 (product/deal-room).

POST /api/room/seller/register  — seller creates a room, gets a token + shareable URL
POST /api/room/buyer/register   — buyer joins a waiting room, gets a token
GET  /api/room/{room_id}/status — polls room status (public, no auth required)

Tokens are random 64-char hex strings stored in the deal_rooms table.
Expiry is 2 hours; the client is expected to re-register when the token expires.
"""
import secrets
import time
import uuid

from fastapi import APIRouter, HTTPException

from app.api.room_schemas import (
    BuyerJoinResponse,
    BuyerRegisterRequest,
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
    """Return current room status. Polled every 3 s by the WaitingRoom UI."""
    room = await db.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    return RoomStatusResponse(
        room_id=room["room_id"],
        status=room["status"],
        seller_name=room["seller_name"],
        buyer_name=room["buyer_name"],
        seller_eth=room["seller_eth"],
        buyer_eth=room["buyer_eth"],
        deal_id=room["deal_id"],
        created_at=room["created_at"],
    )
