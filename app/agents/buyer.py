import json
import anthropic
from app.config import settings

# Phase 2: upgraded from anthropic.Anthropic (sync) to anthropic.AsyncAnthropic
# so that Claude API calls are truly non-blocking inside the async event loop.

BUYER_SYSTEM_PROMPT = """You are a data buyer agent negotiating access to a proprietary dataset inside a Trusted Execution Environment (TEE).

Your goal: acquire the data at the best possible price within your budget.

Budget: {budget}
Requirements: {requirements}

Negotiation strategy:
- Start by offering 60% of your budget.
- Make concessions of 5-10% per round if the seller counters.
- Accept if the price is at or below your budget and terms are acceptable.
- Reject (walk away) if price exceeds your budget or terms are unacceptable.

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|reject", "price": <float>, "terms": {{"access_scope": "<string>", "duration_days": <int>}}, "reasoning": "<string>"}}
"""


class BuyerAgent:
    def __init__(self, budget: float, requirements: str):
        self.budget = budget
        self.requirements = requirements
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = BUYER_SYSTEM_PROMPT.format(
            budget=budget,
            requirements=requirements,
        )

    async def evaluate_offer(self, seller_offer: dict, history: list[dict]) -> dict:
        messages = self._build_messages(history, seller_offer)

        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=self.system_prompt,
            messages=messages,
        )

        raw = response.content[0].text.strip()
        return self._parse_response(raw)

    def _build_messages(self, history: list[dict], current_offer: dict) -> list[dict]:
        messages = []
        for entry in history:
            role = "user" if entry["role"] == "seller" else "assistant"
            messages.append({"role": role, "content": json.dumps(entry["content"])})
        messages.append({"role": "user", "content": f"Seller's offer: {json.dumps(current_offer)}"})
        return messages

    def _parse_response(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Extract first JSON object — model may return extra text after the block
            start = raw.find("{")
            data, _ = json.JSONDecoder().raw_decode(raw, start)

        return {
            "action": data.get("action", "reject"),
            "price": float(data.get("price") or 0),
            "terms": data.get("terms", {}),
            "reasoning": data.get("reasoning", ""),
        }
