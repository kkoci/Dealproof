"""
ArbitratorAgent — binding split proposer.

Called when negotiation exhausts max_rounds without agreement.
Runs inside the same TEE. Proposes a fair settlement price between
seller floor and buyer budget, clamped in code regardless of LLM output.
"""
import json
import logging
import anthropic
from dataclasses import dataclass
from app.config import settings

logger = logging.getLogger(__name__)

_ARBITRATE_PROMPT = """You are a neutral arbitrator inside a Trusted Execution Environment (TEE). A negotiation has deadlocked after exhausting all rounds. You must propose a fair binding settlement.

Buyer budget (hard ceiling): {buyer_budget}
Seller floor price (hard floor): {floor_price}
Negotiation deadlocked after {turn_count} turns.

Transcript:
---
{transcript}
---

Propose a fair settlement price between floor_price and buyer_budget (inclusive). Consider the trajectory of offers and the gap between the last stated positions.

Respond with valid JSON only, no extra text:
{{"price": <float>, "rationale": "<one sentence>"}}"""


@dataclass
class ArbitrationResult:
    proposed_price: float
    rationale: str
    arbitrated: bool = True


class ArbitratorAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def arbitrate(
        self,
        transcript: list[dict],
        buyer_budget: float,
        floor_price: float,
    ) -> ArbitrationResult | None:
        try:
            response = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                messages=[{
                    "role": "user",
                    "content": _ARBITRATE_PROMPT.format(
                        buyer_budget=buyer_budget,
                        floor_price=floor_price,
                        turn_count=len(transcript),
                        transcript=json.dumps(transcript, indent=2),
                    ),
                }],
            )

            raw = response.content[0].text.strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                start = raw.find("{")
                data, _ = json.JSONDecoder().raw_decode(raw, start)

            price = float(data.get("price", (buyer_budget + floor_price) / 2))
            # Clamp within [floor_price, buyer_budget] — code enforces this regardless of LLM output
            price = max(floor_price, min(buyer_budget, price))

            return ArbitrationResult(
                proposed_price=price,
                rationale=str(data.get("rationale", "")),
            )

        except Exception as exc:
            logger.warning(f"ArbitratorAgent: arbitration failed (non-fatal) — {exc}")
            return None
