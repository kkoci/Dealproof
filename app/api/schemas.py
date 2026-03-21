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
from pydantic import BaseModel, Field, field_validator, model_validator


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
    # Phase 4: optional on-chain escrow fields
    seller_address: Optional[str] = Field(
        default=None,
        description=(
            "Ethereum address of the seller (checksummed). When provided alongside "
            "escrow_amount_eth and a configured CONTRACT_ADDRESS, ETH is deposited "
            "into DealProof.sol escrow at deal creation and released on TEE attestation."
        ),
    )
    escrow_amount_eth: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Amount of ETH to deposit as escrow. Required when seller_address is set. "
            "Released to the seller on successful negotiation; refundable after the "
            "negotiation window expires if the deal fails."
        ),
    )

    @field_validator("data_hash")
    @classmethod
    def data_hash_must_be_sha256(cls, v: str) -> str:
        """Reject non-SHA-256 data_hash values at schema level, regardless of whether
        seller_proof is present. A garbage hash would propagate into the DB and
        attestation payload without this guard."""
        _hex = frozenset("0123456789abcdef")
        if not (isinstance(v, str) and len(v) == 64 and all(c in _hex for c in v.lower())):
            raise ValueError(
                f"data_hash must be a 64-char lowercase hex SHA-256 string (got: {v!r})"
            )
        return v.lower()

    @model_validator(mode="after")
    def budget_must_meet_floor(self) -> "DealCreate":
        """
        Reject deals where the buyer's maximum budget is below the seller's
        floor price — negotiation would always fail, wasting API credits.
        Equal values are allowed: the buyer can accept exactly the floor.
        """
        if self.buyer_budget < self.floor_price:
            raise ValueError(
                f"buyer_budget ({self.buyer_budget}) must be >= floor_price ({self.floor_price}). "
                "A deal where the buyer cannot afford the seller's minimum will always fail."
            )
        return self


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
    # Phase 4: on-chain escrow transaction hashes
    escrow_tx: str | None = None        # tx hash of createDeal (escrow deposit)
    completion_tx: str | None = None    # tx hash of completeDeal or refund
    transcript: list[NegotiationRound] = []


class DealStatus(BaseModel):
    deal_id: str
    status: str  # "pending" | "negotiating" | "agreed" | "failed" | "verification_failed"
    result: DealResult | None = None
