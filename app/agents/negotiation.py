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

from app.agents.buyer import BuyerAgent
from app.agents.seller import SellerAgent
from app.tee.attestation import sign_result

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


async def run_negotiation(
    buyer: BuyerAgent,
    seller: SellerAgent,
    max_rounds: int = 10,
    data_hash: str | None = None,  # Phase 3: from Props verification; embedded in the deal attestation
) -> NegotiationResult:
    history: list[dict] = []
    transcript: list[NegotiationRound] = []

    for round_num in range(1, max_rounds + 1):
        logger.info(f"Round {round_num}: seller making offer")

        seller_offer = await seller.make_offer(history)
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
                _build_sign_payload(agreed_price, agreed_terms, data_hash)
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
        transcript.append(
            NegotiationRound(
                round=round_num,
                role="seller",
                action=seller_eval["action"],
                price=seller_eval["price"],
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
                _build_sign_payload(agreed_price, agreed_terms, data_hash)
            )
            return NegotiationResult(
                agreed=True,
                final_price=agreed_price,
                terms=agreed_terms,
                attestation=attestation,
                transcript=transcript,
            )

    logger.info("Max rounds reached without agreement.")
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
