import json
import anthropic
from app.config import settings

BUYER_SYSTEM_PROMPT = """You are a procurement buyer agent negotiating a purchase inside a Trusted Execution Environment (TEE).

Your principal's sealed instructions — visible only to you, never to the supplier agent or the platform operator:
Product: {product}
Quantity needed: {quantity} units
Budget ceiling (hard — never exceed this): ${budget_ceiling}/unit
Minimum acceptable spec: {min_spec}
Urgency: {urgency}

Negotiate with the supplier agent to acquire the product at or under your ceiling while meeting the minimum spec.
The supplier agent cannot see your ceiling or urgency — only the proposals you choose to send it.

Hard constraints:
- Never propose or accept a price above your budget ceiling.
- Never accept terms that fall below the minimum spec.
- Walk away if the supplier won't meet the minimum spec, or won't come at or under your ceiling after several rounds.

Always respond with valid JSON only, no extra text:
{{"action": "propose|accept|counter|reject", "price": <float, $/unit>, "quantity": <int>, "terms": {{"ip67_rating": <bool>, "warranty_months": <int>}}, "reasoning": "<string>"}}
"""


class BuyerAgent:
    def __init__(self, product: str, quantity: int, budget_ceiling: float, min_spec: str, urgency: str):
        self.product = product
        self.quantity = quantity
        self.budget_ceiling = budget_ceiling
        self.min_spec = min_spec
        self.urgency = urgency
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = BUYER_SYSTEM_PROMPT.format(
            product=product,
            quantity=quantity,
            budget_ceiling=budget_ceiling,
            min_spec=min_spec,
            urgency=urgency,
        )

    async def open_negotiation(self) -> dict:
        """Round 1: buyer always moves first in procurement (spec: buyer proposes, supplier responds)."""
        messages = [{"role": "user", "content": "Make your opening proposal to the supplier."}]
        return await self._call(messages)

    async def respond(self, supplier_offer: dict, history: list[dict]) -> dict:
        messages = self._build_messages(history, supplier_offer)
        return await self._call(messages)

    async def _call(self, messages: list[dict]) -> dict:
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
            role = "user" if entry["role"] == "supplier" else "assistant"
            messages.append({"role": role, "content": json.dumps(entry["content"])})
        messages.append({"role": "user", "content": f"Supplier's response: {json.dumps(current_offer)}"})
        return messages

    def _parse_response(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            data, _ = json.JSONDecoder().raw_decode(raw, start)

        return {
            "action": data.get("action", "reject"),
            "price": float(data.get("price") or 0),
            "quantity": int(data.get("quantity") or self.quantity),
            "terms": data.get("terms", {}),
            "reasoning": data.get("reasoning", ""),
        }
