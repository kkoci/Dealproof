import json
import anthropic
from app.config import settings

SUPPLIER_SYSTEM_PROMPT = """You are a procurement supplier agent negotiating a sale inside a Trusted Execution Environment (TEE).

Your principal's sealed instructions — visible only to you, never to the buyer agent or the platform operator:
Product: {product}
Price floor for orders of {bulk_threshold}+ units (hard — never go below this): ${floor_price_bulk}/unit
Price floor for orders below {bulk_threshold} units (hard — never go below this): ${floor_price_standard}/unit
Available inventory: {available_inventory} units
Delivery lead time: {lead_time_days} business days

Negotiate with the buyer agent to maximise revenue while staying within your inventory and lead-time constraints.
The buyer agent cannot see your floor prices or inventory — only the proposals you choose to send it.

Hard constraints:
- Never accept or counter below the floor price that applies to the requested order quantity.
- Never promise more units than you have in inventory.
- Reject if the buyer won't move above your floor after several rounds.

Terms negotiation:
- Price is the primary lever. Be flexible on warranty and delivery timing if price is right.

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|reject", "price": <float, $/unit>, "quantity": <int>, "terms": {{"ip67_rating": <bool>, "warranty_months": <int>, "lead_time_days": <int>}}, "reasoning": "<string>"}}
"""


class SupplierAgent:
    def __init__(
        self,
        product: str,
        floor_price_bulk: float,
        floor_price_standard: float,
        bulk_threshold: int,
        available_inventory: int,
        lead_time_days: int,
    ):
        self.product = product
        self.floor_price_bulk = floor_price_bulk
        self.floor_price_standard = floor_price_standard
        self.bulk_threshold = bulk_threshold
        self.available_inventory = available_inventory
        self.lead_time_days = lead_time_days
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = SUPPLIER_SYSTEM_PROMPT.format(
            product=product,
            floor_price_bulk=floor_price_bulk,
            floor_price_standard=floor_price_standard,
            bulk_threshold=bulk_threshold,
            available_inventory=available_inventory,
            lead_time_days=lead_time_days,
        )

    async def respond(self, buyer_offer: dict, history: list[dict]) -> dict:
        messages = self._build_messages(history, buyer_offer)
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
            role = "user" if entry["role"] == "buyer" else "assistant"
            messages.append({"role": role, "content": json.dumps(entry["content"])})
        messages.append({"role": "user", "content": f"Buyer's proposal: {json.dumps(current_offer)}"})
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
            "quantity": int(data.get("quantity") or 0),
            "terms": data.get("terms", {}),
            "reasoning": data.get("reasoning", ""),
        }
