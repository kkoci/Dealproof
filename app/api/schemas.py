"""
API schemas — Phase 6.

Changes from Phase 3:
  - DealCreate gains optional seller_email_eml field (Phase 6 DKIM email proof).
    When present, the base64-encoded .eml is verified inside the TEE before
    negotiation.  The sending domain is injected into the seller agent's system
    prompt as a TEE-verified credential.  The raw email body is never stored.
  - DealResult gains dkim_verification field: the result of DKIM verification
    {domain, verified, dns_unavailable, error}.
  - DCAPVerification response model added for Phase 7 DCAP quote inspection.

Changes from Phase 2→3 are preserved unchanged (seller_proof, data_verification_attestation).
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
    # Phase 6: optional DKIM email proof — base64-encoded .eml file from the seller.
    # The TEE verifies the DKIM signature via DNS, extracts the sending domain, and
    # injects a TEE-verified credential into the seller agent before negotiation starts.
    # The raw email bytes are never stored; only the domain + verified flag are retained.
    seller_email_eml: Optional[str] = Field(
        default=None,
        description=(
            "Base64-encoded .eml file providing a DKIM email proof of seller identity. "
            "The TEE verifies the DKIM signature and extracts the sending domain "
            "(e.g. 'acme.com'). This domain is injected as a TEE-verified credential "
            "into the seller agent's negotiation context. The raw email body is discarded "
            "immediately after verification and is never persisted."
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
    # Phase 6: DKIM verification result (present when seller_email_eml was supplied)
    dkim_verification: dict | None = None
    transcript: list[NegotiationRound] = []


class DealStatus(BaseModel):
    deal_id: str
    status: str  # "pending" | "negotiating" | "agreed" | "failed" | "verification_failed"
    result: DealResult | None = None


class DCAPVerification(BaseModel):
    """
    Phase 7: Structured result from parsing a TDX attestation quote.

    In simulation mode the quote is a hex-encoded SHA-256 string prefixed with
    'sim_quote:'.  In production it is a raw TDX quote binary encoded as hex.

    Fields
    ------
    deal_id : str
    mode : "simulation" | "production"
        Whether this quote came from a simulated or real TEE.
    version : int | None
        DCAP quote version (from the 2-byte header field). None for simulation.
    tee_type : str | None
        Decoded TEE type string (e.g. "TDX" for 0x00000081). None for simulation.
    qe_vendor_id : str | None
        16-byte QE vendor UUID hex string. Intel's QE has a fixed known value.
        None for simulation.
    report_data_hex : str | None
        First 32 bytes of the TD report_data field, hex-encoded.
        In DealProof this equals SHA-256(json(deal_terms)).  None for simulation.
    deal_terms_hash : str | None
        Same as report_data_hex — shown as a labeled alias for UI clarity.
    verification_status : str
        "simulation_only" | "dcap_header_parsed" | "invalid_quote"
    error : str | None
        Human-readable error if parsing failed.
    """

    deal_id: str
    mode: str
    version: int | None = None
    tee_type: str | None = None
    qe_vendor_id: str | None = None
    report_data_hex: str | None = None
    deal_terms_hash: str | None = None
    verification_status: str
    error: str | None = None
