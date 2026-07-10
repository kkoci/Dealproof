"""
Agent Rail — Phase 2 API schemas.

Pydantic request/response models for POST /api/agentrail/deals, GET
/api/agentrail/deals/{id}, and GET /api/agentrail/deals/{id}/attest.

Kept separate from app/agentrail/schemas.py (the dataclasses the negotiation
engine itself uses) the same way DealProof core separates app/api/schemas.py
from app/agents' internal types.

Privacy note: BuyerParametersIn / SupplierParametersIn are request-only —
DealStatusResponse never echoes them back. Only the negotiated proposals
(ProcurementRoundOut) and the final agreed terms are ever returned by the API.
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


class AttestResponse(BaseModel):
    deal_id: str
    attestation: str
    valid: bool
    mode: str
    mrenclave: str | None = None
    byte_length: int
