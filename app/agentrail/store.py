"""
In-memory deal store — Phase 2.

No database, per build_spec_agent_rail.md ("No auth, no database — in-memory
state is fine for demo mode"). State is lost on process restart; that's
acceptable for a shareable demo, not for Phase 3 production use.

Only ever holds transcript rounds and the final agreed terms — never the
sealed BuyerParameters/SupplierParameters the request carried in. That's what
keeps GET /api/agentrail/deals/{id} safe to expose publicly: there is nothing
sealed left in the record to leak.
"""
from dataclasses import dataclass, field

from app.agentrail.schemas import ProcurementRound

STATUS_NEGOTIATING = "negotiating"
STATUS_AGREED = "agreed"
STATUS_NO_DEAL = "no_deal"
STATUS_FAILED = "failed"


@dataclass
class DealRecord:
    deal_id: str
    max_rounds: int
    status: str = STATUS_NEGOTIATING
    transcript: list[ProcurementRound] = field(default_factory=list)
    final_price: float | None = None
    final_quantity: int | None = None
    terms: dict | None = None
    attestation: str | None = None
    error: str | None = None


_deals: dict[str, DealRecord] = {}


def create(deal_id: str, max_rounds: int) -> DealRecord:
    record = DealRecord(deal_id=deal_id, max_rounds=max_rounds)
    _deals[deal_id] = record
    return record


def get(deal_id: str) -> DealRecord | None:
    return _deals.get(deal_id)


def append_round(deal_id: str, round_: ProcurementRound) -> None:
    record = _deals.get(deal_id)
    if record is not None:
        record.transcript.append(round_)


def mark_agreed(deal_id: str, final_price: float, final_quantity: int, terms: dict, attestation: str) -> None:
    record = _deals.get(deal_id)
    if record is not None:
        record.status = STATUS_AGREED
        record.final_price = final_price
        record.final_quantity = final_quantity
        record.terms = terms
        record.attestation = attestation


def mark_no_deal(deal_id: str) -> None:
    record = _deals.get(deal_id)
    if record is not None:
        record.status = STATUS_NO_DEAL


def mark_failed(deal_id: str, error: str) -> None:
    record = _deals.get(deal_id)
    if record is not None:
        record.status = STATUS_FAILED
        record.error = error
