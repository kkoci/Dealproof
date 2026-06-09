"""
Negotiation loop — Phase 3.

Changes from Phase 2:
  - run_negotiation() accepts an optional `data_hash` parameter supplied by
    the Props verification layer (Phase 3).
  - When data_hash is provided, sign_result() is called with a combined
    payload covering BOTH the deal terms AND the data provenance:
      {final_price, terms, data_hash, data_verified: True}
    This produces a single TDX quote that simultaneously proves the
    negotiation outcome and references the verified dataset hash — a buyer
    or auditor needs only one quote to confirm the full picture.
  - When data_hash is None (no seller_proof submitted), the sign_result
    payload is unchanged from Phase 2: {final_price, terms}.
"""
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.agents.buyer import BuyerAgent
from app.agents.seller import SellerAgent
from app.tee.attestation import sign_result

if TYPE_CHECKING:
    from app.agents.arbitrator import ArbitratorAgent

logger = logging.getLogger(__name__)


@dataclass
class NegotiationRound:
    round: int
    role: str
    action: str
    price: float
    terms: dict
    reasoning: str


@dataclass
class NegotiationResult:
    agreed: bool
    final_price: float | None = None
    terms: dict | None = None
    attestation: str | None = None  # TDX quote from tappd (Phase 2+); includes data_hash when Phase 3 proof present
    transcript: list[NegotiationRound] = field(default_factory=list)
    arbitrated: bool = False  # True when ArbitratorAgent resolved a deadlock


def _normalise_action(response: dict, valid: set[str], default: str) -> dict:
    """
    Ensure the 'action' field in an agent response is a known value.

    If Claude returns null, an empty string, or an unexpected action string,
    we fall back to `default` rather than letting the negotiation loop silently
    misbehave.  The original response dict is copied so callers' history is
    not mutated.
    """
    action = response.get("action")
    if not isinstance(action, str) or action.lower() not in valid:
        logger.warning(
            f"Unexpected action value {action!r} — normalising to '{default}'"
        )
        response = dict(response)
        response["action"] = default
        # If price is missing or zero after a bad response, preserve the last
        # known price by leaving it at whatever _parse_response returned (0.0).
        # The negotiation loop's price-tracking handles 0.0 gracefully via the
        # existing `data.get("price") or 0` pattern.
    return response


async def run_negotiation(
    buyer: BuyerAgent,
    seller: SellerAgent,
    max_rounds: int = 10,
    data_hash: str | None = None,  # Phase 3: from Props verification; embedded in the deal attestation
    memory_hash: str = "",  # SHA-256 of buyer+seller memory state; included in attestation when non-empty
    arbitrator: "ArbitratorAgent | None" = None,  # when set, resolves deadlocks instead of returning agreed=False
) -> NegotiationResult:
    history: list[dict] = []
    transcript: list[NegotiationRound] = []

    for round_num in range(1, max_rounds + 1):
        logger.info(f"Round {round_num}: seller making offer")

        seller_offer = await seller.make_offer(history)
        seller_offer = _normalise_action(seller_offer, valid={"offer", "counter", "accept", "reject"}, default="counter")
        logger.info(f"Seller: {seller_offer}")

        transcript.append(
            NegotiationRound(
                round=round_num,
                role="seller",
                action=seller_offer["action"],
                price=seller_offer["price"],
                terms=seller_offer.get("terms", {}),
                reasoning=seller_offer.get("reasoning", ""),
            )
        )
        history.append({"role": "seller", "content": seller_offer})

        if seller_offer["action"] == "reject":
            logger.info("Seller rejected. Deal failed.")
            return NegotiationResult(agreed=False, transcript=transcript)

        logger.info(f"Round {round_num}: buyer evaluating offer")
        buyer_response = await buyer.evaluate_offer(seller_offer, history[:-1])
        buyer_response = _normalise_action(buyer_response, valid={"accept", "counter", "reject"}, default="counter")
        logger.info(f"Buyer: {buyer_response}")

        transcript.append(
            NegotiationRound(
                round=round_num,
                role="buyer",
                action=buyer_response["action"],
                price=buyer_response["price"],
                terms=buyer_response.get("terms", {}),
                reasoning=buyer_response.get("reasoning", ""),
            )
        )
        history.append({"role": "buyer", "content": buyer_response})

        if buyer_response["action"] == "accept":
            agreed_price = seller_offer["price"]
            agreed_terms = seller_offer.get("terms", {})
            logger.info(f"Deal agreed at {agreed_price} — requesting TEE attestation")
            attestation = await sign_result(
                _build_sign_payload(agreed_price, agreed_terms, data_hash),
                memory_hash=memory_hash,
            )
            return NegotiationResult(
                agreed=True,
                final_price=agreed_price,
                terms=agreed_terms,
                attestation=attestation,
                transcript=transcript,
            )

        if buyer_response["action"] == "reject":
            logger.info("Buyer rejected. Deal failed.")
            return NegotiationResult(agreed=False, transcript=transcript)

        # Re-query seller with the buyer's counter offer
        history_check = list(history)
        seller_eval = await seller.make_offer(history_check)
        seller_eval = _normalise_action(seller_eval, valid={"offer", "counter", "accept", "reject"}, default="counter")

        # When the seller accepts, the deal closes at the buyer's counter price.
        # Override the transcript price so it matches the actual agreed amount —
        # the seller's stated price on an accept is unreliable (the LLM may echo
        # its own last ask rather than the buyer's counter).
        transcript_price = (
            buyer_response["price"]
            if seller_eval["action"] == "accept"
            else seller_eval["price"]
        )
        transcript.append(
            NegotiationRound(
                round=round_num,
                role="seller",
                action=seller_eval["action"],
                price=transcript_price,
                terms=seller_eval.get("terms", {}),
                reasoning=seller_eval.get("reasoning", ""),
            )
        )
        history.append({"role": "seller", "content": seller_eval})

        if seller_eval["action"] == "accept":
            agreed_price = buyer_response["price"]
            agreed_terms = buyer_response.get("terms", {})
            logger.info(
                f"Seller accepted buyer counter at {agreed_price} — requesting TEE attestation"
            )
            attestation = await sign_result(
                _build_sign_payload(agreed_price, agreed_terms, data_hash),
                memory_hash=memory_hash,
            )
            return NegotiationResult(
                agreed=True,
                final_price=agreed_price,
                terms=agreed_terms,
                attestation=attestation,
                transcript=transcript,
            )

    logger.info("Max rounds reached without agreement.")

    if arbitrator is not None:
        logger.info("Attempting arbitration to resolve deadlock.")
        transcript_data = [
            {"round": r.round, "role": r.role, "action": r.action, "price": r.price}
            for r in transcript
        ]
        arbitration = await arbitrator.arbitrate(transcript_data, buyer.budget, seller.floor_price)
        if arbitration is not None:
            logger.info(f"Arbitrated settlement at {arbitration.proposed_price} — requesting TEE attestation")
            attestation = await sign_result(
                _build_sign_payload(arbitration.proposed_price, {}, data_hash),
                memory_hash=memory_hash,
            )
            return NegotiationResult(
                agreed=True,
                final_price=arbitration.proposed_price,
                terms={},
                attestation=attestation,
                transcript=transcript,
                arbitrated=True,
            )
        logger.warning("Arbitration returned None — falling back to no agreement.")

    return NegotiationResult(agreed=False, transcript=transcript)


def _build_sign_payload(price: float, terms: dict, data_hash: str | None) -> dict:
    """
    Build the payload that will be SHA-256 hashed and embedded in the TDX
    report_data field.

    Without Phase 3 proof:  {final_price, terms}
    With Phase 3 proof:     {final_price, terms, data_hash, data_verified: True}

    The combined payload means a single TDX quote covers both the negotiated
    outcome and the dataset provenance reference.
    """
    payload: dict = {"final_price": price, "terms": terms}
    if data_hash is not None:
        payload["data_hash"] = data_hash
        payload["data_verified"] = True
    return payload
