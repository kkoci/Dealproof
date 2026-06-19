"""Schemas for the Deal Room auth + session layer — Phase 1+2 (product/deal-room)."""
from typing import Optional, Any
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
    status: str  # waiting | ready | configuring | confirmed | running | complete | failed
    seller_name: Optional[str] = None
    buyer_name: Optional[str] = None
    seller_eth: Optional[str] = None
    buyer_eth: Optional[str] = None
    deal_id: Optional[str] = None
    created_at: Optional[str] = None
    deal_payload: Optional[dict] = None   # Phase 2: deal config (no floor_price for buyer)
    seller_confirmed: bool = False         # Phase 2
    buyer_confirmed: bool = False          # Phase 2


# ── Phase 2 ────────────────────────────────────────────────────────────────

class DealConfigRequest(BaseModel):
    data_description: str = Field(..., min_length=1)
    dataset_type: str = Field(
        default="custom",
        description="iot_sensor | financial_transactions | ml_training | transcripts | custom",
    )
    asking_price: float = Field(..., gt=0, description="Displayed asking price (shown to buyer)")
    floor_price: float = Field(..., gt=0, description="Minimum acceptable price (never shown to buyer)")
    buyer_budget: float = Field(..., gt=0)
    buyer_requirements: str = Field(default="")
    quality_enabled: bool = False
    quality_null_rate_threshold: float = Field(default=0.1, ge=0, le=1)
    quality_completeness_min: float = Field(default=0.9, ge=0, le=1)
    quality_schema_consistency: bool = True
    escrow_enabled: bool = False
    escrow_eth_address: Optional[str] = None
    # Phase 5: dataset upload result — populated by POST /dataset before config is saved
    corpus_root: Optional[str] = None        # Merkle root of uploaded file (used as data_hash)
    seller_proof: Optional[dict] = None      # chunk_hashes + root_hash for Props verification
    quality_metrics: Optional[dict] = None   # DataQualityMetrics-shaped dict from quality preview


class ConfirmResponse(BaseModel):
    role_confirmed: str  # "seller" | "buyer"
    seller_confirmed: bool
    buyer_confirmed: bool
    status: str
