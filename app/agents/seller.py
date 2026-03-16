import json
import anthropic
from app.config import settings

# Phase 2: upgraded from anthropic.Anthropic (sync) to anthropic.AsyncAnthropic
# so that Claude API calls are truly non-blocking inside the async event loop.

SELLER_SYSTEM_PROMPT = """You are a data seller agent negotiating access to your proprietary dataset inside a Trusted Execution Environment (TEE).

Your goal: maximise revenue while protecting data integrity.

Minimum acceptable price (floor): {floor_price}
Data description: {data_description}

Negotiation strategy:
- Open by asking 40% above your floor price.
- Come down by 5-10% per round if the buyer counters reasonably.
- Accept if the offered price meets or exceeds your floor.
- Reject if the buyer's price is below your floor after 2+ rounds of negotiation.

Always respond with valid JSON only, no extra text:
{{"action": "offer|counter|accept|reject", "price": <float>, "terms": {{"access_scope": "<string>", "duration_days": <int>}}, "reasoning": "<string>"}}
"""


class SellerAgent:
    def __init__(self, floor_price: float, data_description: str):
        self.floor_price = floor_price
        self.data_description = data_description
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = SELLER_SYSTEM_PROMPT.format(
            floor_price=floor_price,
            data_description=data_description,
        )

    async def make_offer(self, history: list[dict]) -> dict:
        messages = self._build_messages(history)

        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=self.system_prompt,
            messages=messages,
        )

        raw = response.content[0].text.strip()
        return self._parse_response(raw)

    def _build_messages(self, history: list[dict]) -> list[dict]:
        if not history:
            return [{"role": "user", "content": "Start the negotiation. Make your opening offer."}]

        messages = []
        for entry in history:
            role = "user" if entry["role"] == "buyer" else "assistant"
            messages.append({"role": role, "content": json.dumps(entry["content"])})

        # Ensure last message is from user
        if messages and messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": "Continue the negotiation based on the buyer's last response."})

        return messages

    def _parse_response(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])

        return {
            "action": data.get("action", "offer"),
            "price": float(data.get("price") or 0),
            "terms": data.get("terms", {}),
            "reasoning": data.get("reasoning", ""),
        }
