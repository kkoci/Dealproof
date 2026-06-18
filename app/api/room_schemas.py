"""Schemas for the Deal Room auth + session layer — Phase 1 (product/deal-room)."""
from typing import Optional
from pydantic import BaseModel, Field


class SellerRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    eth_address: Optional[str] = None


class BuyerRegisterRequest(BaseModel):
    room_id: str = Field(..., description="Room ID from the shareable URL")
    name: str = Field(..., min_length=1)
    eth_address: Optional[str] = None


class RoomCreateResponse(BaseModel):
    room_id: str
    room_url: str
    seller_token: str
    expires_at: int  # Unix timestamp


class BuyerJoinResponse(BaseModel):
    buyer_token: str
    room_id: str
    seller_name: str
    expires_at: int  # Unix timestamp


class RoomStatusResponse(BaseModel):
    room_id: str
    status: str  # waiting | ready | running | complete | failed
    seller_name: Optional[str] = None
    buyer_name: Optional[str] = None
    seller_eth: Optional[str] = None
    buyer_eth: Optional[str] = None
    deal_id: Optional[str] = None
    created_at: Optional[str] = None
