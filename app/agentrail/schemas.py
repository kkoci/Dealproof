"""
Agent Rail — Phase 1 dataclasses.

Kept separate from app/agents (the data-deal negotiation) and app/api/schemas.py
(the DealProof core Pydantic models) because Agent Rail negotiates procurement
terms (price/unit, quantity, spec) rather than dataset access terms.
"""
from dataclasses import dataclass, field


@dataclass
class BuyerParameters:
    """Sealed buyer-side procurement parameters. Only ever injected into
    BuyerAgent's own system prompt — never passed to SupplierAgent or logged."""
    product: str
    quantity: int
    budget_ceiling: float  # $/unit, hard ceiling
    min_spec: str
    urgency: str


@dataclass
class SupplierParameters:
    """Sealed supplier-side procurement parameters. Only ever injected into
    SupplierAgent's own system prompt — never passed to BuyerAgent or logged."""
    product: str
    floor_price_bulk: float      # $/unit floor for orders >= bulk_threshold
    floor_price_standard: float  # $/unit floor for orders < bulk_threshold
    bulk_threshold: int
    available_inventory: int
    lead_time_days: int


@dataclass
class ProcurementRound:
    round: int
    role: str  # "buyer" | "supplier"
    action: str
    price: float
    quantity: int
    terms: dict
    reasoning: str


@dataclass
class ProcurementResult:
    agreed: bool
    final_price: float | None = None
    final_quantity: int | None = None
    terms: dict | None = None
    attestation: str | None = None  # TDX quote from tappd, via app.tee.attestation.sign_result
    transcript: list[ProcurementRound] = field(default_factory=list)
