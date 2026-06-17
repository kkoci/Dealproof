import json
import anthropic
from app.config import settings

# Phase 2: upgraded from anthropic.Anthropic (sync) to anthropic.AsyncAnthropic
# so that Claude API calls are truly non-blocking inside the async event loop.

_MEMORY_BLOCK = """

[MEMORY CONTEXT — recalled from prior negotiations inside this TEE]
{memory_context}

Act on this. Adjust your opening offer and concession pace based on what you remember about this counterparty.
"""

_QUALITY_BLOCK = """

[TEE-VERIFIED DATASET QUALITY CREDENTIAL]
An independent DataQualityAgent assessed this dataset inside the TEE before negotiation began.
Its findings are cryptographically attested and cannot be disputed by the seller.

{quality_context}

Use this in negotiation. If quality is medium or low, open lower and cite specific issues.
"""

BUYER_SYSTEM_PROMPT = """You are a data buyer agent negotiating access to a proprietary dataset inside a Trusted Execution Environment (TEE).

Your goal: acquire the data at the best possible price within your budget.

Budget (hard ceiling — never exceed this): {budget}
Requirements: {requirements}

Use your judgment to negotiate. If you have memory context from prior deals with this counterparty, use it actively — adjust your opening offer, concession pace, and walk-away threshold based on what you remember. A seller who previously accepted quickly near floor price should get a lower opening offer from you. A seller who held firm should get a higher opening to avoid wasted rounds.

Hard constraints:
- Never offer above your budget.
- Walk away if the seller won't come below your budget after several rounds.

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|reject", "price": <float>, "terms": {{"access_scope": "<string>", "duration_days": <int>}}, "reasoning": "<string>"}}
"""


class BuyerAgent:
    def __init__(self, budget: float, requirements: str, memory_context: str = "", quality_context: str = ""):
        self.budget = budget
        self.requirements = requirements
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = BUYER_SYSTEM_PROMPT.format(
            budget=budget,
            requirements=requirements,
        )
        if memory_context:
            self.system_prompt += _MEMORY_BLOCK.format(memory_context=memory_context)
        if quality_context:
            self.system_prompt += _QUALITY_BLOCK.format(quality_context=quality_context)

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
