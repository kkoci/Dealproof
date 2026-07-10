"""
Enclave mediator — Phase 1.

Runs the buyer/supplier negotiation loop that, in production, executes inside
the Phala Cloud TDX enclave alongside the rest of DealProof. Each agent's
system prompt is built from only its own principal's sealed parameters
(BuyerParameters / SupplierParameters) — the mediator never constructs a
message that contains the opposing side's sealed values, so the buyer's
budget_ceiling and the supplier's floor prices are structurally unreachable
by the other agent. The transcript logged here carries only the JSON actions
agents exchange (action, price, quantity, terms, reasoning) — never the
sealed parameter objects.

Mirrors app/agents/negotiation.py's run_negotiation() loop shape, with the
buyer moving first (procurement convention: buyer issues the RFQ/proposal,
supplier responds) instead of the seller-opens pattern used for data deals.
"""
import logging

from app.agentrail.buyer_agent import BuyerAgent
from app.agentrail.supplier_agent import SupplierAgent
from app.agentrail.schemas import ProcurementRound, ProcurementResult
from app.tee.attestation import sign_result

logger = logging.getLogger(__name__)


def _normalise_action(response: dict, valid: set[str], default: str) -> dict:
    action = response.get("action")
    if not isinstance(action, str) or action.lower() not in valid:
        logger.warning(f"Unexpected action value {action!r} — normalising to '{default}'")
        response = dict(response)
        response["action"] = default
    return response


def _round(round_num: int, role: str, action: dict) -> ProcurementRound:
    return ProcurementRound(
        round=round_num,
        role=role,
        action=action["action"],
        price=action["price"],
        quantity=action["quantity"],
        terms=action.get("terms", {}),
        reasoning=action.get("reasoning", ""),
    )


async def run_procurement_negotiation(
    buyer: BuyerAgent,
    supplier: SupplierAgent,
    max_rounds: int = 5,
) -> ProcurementResult:
    history: list[dict] = []
    transcript: list[ProcurementRound] = []
    buyer_action: dict = {}
    supplier_action: dict = {}

    for round_num in range(1, max_rounds + 1):
        if round_num == 1:
            logger.info("Round 1: buyer opening proposal")
            buyer_action = await buyer.open_negotiation()
            buyer_action = _normalise_action(
                buyer_action, valid={"propose", "counter", "accept", "reject"}, default="propose"
            )
        else:
            logger.info(f"Round {round_num}: buyer responding to supplier's counter")
            buyer_action = await buyer.respond(supplier_action, history)
            buyer_action = _normalise_action(
                buyer_action, valid={"accept", "counter", "reject"}, default="counter"
            )
        logger.info(f"Buyer action: {buyer_action}")
        transcript.append(_round(round_num, "buyer", buyer_action))
        history.append({"role": "buyer", "content": buyer_action})

        if buyer_action["action"] == "reject":
            logger.info("Buyer rejected. No deal.")
            return ProcurementResult(agreed=False, transcript=transcript)

        if buyer_action["action"] == "accept":
            # Buyer is accepting the supplier's most recent counter (previous round).
            logger.info(f"Buyer accepted at {supplier_action['price']}/unit — requesting TEE attestation")
            return await _close(supplier_action, transcript)

        logger.info(f"Round {round_num}: supplier responding")
        supplier_action = await supplier.respond(buyer_action, history)
        supplier_action = _normalise_action(
            supplier_action, valid={"accept", "counter", "reject"}, default="counter"
        )
        logger.info(f"Supplier action: {supplier_action}")
        transcript.append(_round(round_num, "supplier", supplier_action))
        history.append({"role": "supplier", "content": supplier_action})

        if supplier_action["action"] == "reject":
            logger.info("Supplier rejected. No deal.")
            return ProcurementResult(agreed=False, transcript=transcript)

        if supplier_action["action"] == "accept":
            # Supplier is accepting the buyer's most recent proposal (this round).
            logger.info(f"Supplier accepted at {buyer_action['price']}/unit — requesting TEE attestation")
            return await _close(buyer_action, transcript)

    logger.info("Max rounds reached without agreement.")
    return ProcurementResult(agreed=False, transcript=transcript)


async def _close(agreed_action: dict, transcript: list[ProcurementRound]) -> ProcurementResult:
    payload = {
        "final_price": agreed_action["price"],
        "final_quantity": agreed_action["quantity"],
        "terms": agreed_action.get("terms", {}),
    }
    attestation = await sign_result(payload)
    return ProcurementResult(
        agreed=True,
        final_price=agreed_action["price"],
        final_quantity=agreed_action["quantity"],
        terms=agreed_action.get("terms", {}),
        attestation=attestation,
        transcript=transcript,
    )
