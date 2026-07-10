"""
Agent Rail — API schemas (Phase 2 deal lifecycle + Phase 3 escrow/credential).

Pydantic request/response models for the app.agentrail.routes endpoints.

Kept separate from app/agentrail/schemas.py (the dataclasses the negotiation
engine itself uses) the same way DealProof core separates app/api/schemas.py
from app/agents' internal types.

Privacy note: BuyerParametersIn / SupplierParametersIn are request-only —
DealStatusResponse never echoes them back. Only the negotiated proposals
(ProcurementRoundOut), the final agreed terms, and the redacted conduct
credential (see app/agentrail/credential.py) are ever returned by the API.
"""
from pydantic import BaseModel, Field


class BuyerParametersIn(BaseModel):
    product: str
    quantity: int = Field(..., gt=0)
    budget_ceiling: float = Field(..., gt=0, description="$/unit, hard ceiling — sealed, never echoed back")
    min_spec: str
    urgency: str = "moderate"


class SupplierParametersIn(BaseModel):
    product: str
    floor_price_bulk: float = Field(..., gt=0, description="$/unit floor for orders >= bulk_threshold — sealed")
    floor_price_standard: float = Field(..., gt=0, description="$/unit floor below bulk_threshold — sealed")
    bulk_threshold: int = Field(..., gt=0)
    available_inventory: int = Field(..., gt=0)
    lead_time_days: int = Field(..., gt=0)


class DealCreateRequest(BaseModel):
    buyer: BuyerParametersIn
    supplier: SupplierParametersIn
    max_rounds: int = Field(default=5, gt=0, le=10)
    # Phase 3: optional on-chain escrow. Mirrors DealCreate's seller_address/
    # escrow_amount_eth in DealProof core. When both are set and
    # AGENTRAIL_CONTRACT_ADDRESS is configured, ETH is deposited into
    # AgentDealEscrow at deal creation and released when the deal agrees.
    # Not deployed anywhere as of Phase 3 — see app/agentrail/escrow.py.
    supplier_address: str | None = Field(
        default=None,
        description="Ethereum address of the supplier (checksummed). Required for escrow deposit.",
    )
    escrow_amount_eth: float | None = Field(
        default=None, gt=0, description="Amount of ETH to deposit as escrow. Required when supplier_address is set.",
    )


class DealCreateResponse(BaseModel):
    deal_id: str
    status: str  # "negotiating"


class ProcurementRoundOut(BaseModel):
    round: int
    role: str
    action: str
    price: float
    quantity: int
    terms: dict
    reasoning: str


class DealStatusResponse(BaseModel):
    deal_id: str
    status: str  # "negotiating" | "agreed" | "no_deal" | "failed"
    max_rounds: int
    transcript: list[ProcurementRoundOut]
    final_price: float | None = None
    final_quantity: int | None = None
    terms: dict | None = None
    attestation: str | None = None
    error: str | None = None
    # Phase 3
    picreds_hash: str | None = None
    picreds_attested: bool = False
    escrow_tx: str | None = None       # deposit transaction, set at creation if escrow fields were provided
    settlement_tx: str | None = None   # release transaction, set once the deal agrees and escrow was deposited


class AttestResponse(BaseModel):
    deal_id: str
    attestation: str
    valid: bool
    mode: str
    mrenclave: str | None = None
    byte_length: int


class ConductCheckOut(BaseModel):
    passed: bool
    finding: str


class CredentialResponse(BaseModel):
    """Phase 3 — GET /api/agentrail/deals/{id}/credential.

    audit_result never contains the buyer's budget ceiling or the supplier's
    floor prices — see app/agentrail/credential.py for why and how.
    """
    deal_id: str
    credential_type: str  # "conduct"
    checks: dict[str, ConductCheckOut]
    genuine_negotiation: bool
    final_price: float
    picreds_hash: str
