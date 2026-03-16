"""
API schemas — Phase 3.

Changes from Phase 2:
  - DealCreate gains optional seller_proof field (Phase 3 Props layer).
    If omitted, verification is skipped and the deal runs with basic
    hash-format validation only (Phase 1/2 backward-compatible behaviour).
    If provided, full Merkle verification runs inside the TEE before
    negotiation starts.
  - DealResult gains data_verification_attestation field: the TDX quote
    produced by verify_data_authenticity(), separate from the negotiation
    attestation.  Both are present when seller_proof was supplied and the
    deal was agreed.
"""
from typing import Optional
from pydantic import BaseModel, Field


class DealCreate(BaseModel):
    buyer_budget: float = Field(..., gt=0, description="Maximum the buyer will pay")
    buyer_requirements: str = Field(..., description="What the buyer needs from the data")
    data_description: str = Field(..., description="What the seller is offering")
    data_hash: str = Field(..., description="SHA-256 hash of the dataset (64 hex chars)")
    floor_price: float = Field(..., gt=0, description="Minimum price the seller will accept")
    # Phase 3: optional Props verification proof from the seller
    seller_proof: Optional[dict] = Field(
        default=None,
        description=(
            "Props-layer proof dict. Required fields: root_hash (sha256 hex), "
            "chunk_hashes (list of sha256 hex), chunk_count (int), algorithm ('sha256'). "
            "When present, data authenticity is verified inside the TEE before negotiation starts. "
            "If omitted, only basic hash-format validation is performed."
        ),
    )


class NegotiationRound(BaseModel):
    round: int
    role: str
    action: str
    price: float
    terms: dict
    reasoning: str


class DealResult(BaseModel):
    deal_id: str
    agreed: bool
    final_price: float | None = None
    terms: dict | None = None
    # Phase 2: TDX quote from negotiation (covers final_price + terms + optional data_hash)
    attestation: str | None = None
    # Phase 3: TDX quote from Props verification (covers data_hash + verified + chunk_count)
    data_verification_attestation: str | None = None
    transcript: list[NegotiationRound] = []


class DealStatus(BaseModel):
    deal_id: str
    status: str  # "pending" | "negotiating" | "agreed" | "failed" | "verification_failed"
    result: DealResult | None = None
