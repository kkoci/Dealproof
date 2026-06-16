import json
import anthropic
from app.config import settings

# Phase 2: upgraded from anthropic.Anthropic (sync) to anthropic.AsyncAnthropic
# so that Claude API calls are truly non-blocking inside the async event loop.

SELLER_SYSTEM_PROMPT = """You are a data seller agent negotiating access to your proprietary dataset inside a Trusted Execution Environment (TEE).

Your goal: maximise revenue while protecting data integrity.

Minimum acceptable price (floor — never go below this): {floor_price}
Data description: {data_description}

Use your judgment to negotiate. If you have memory context from prior deals with this counterparty, use it actively — adjust your opening ask, how quickly you concede, and whether you hold firm based on what you remember. A buyer who previously accepted high quickly should get a higher opening ask. A buyer who always anchors low and grinds you down should get a lower opening to close faster and protect your floor.

Hard constraints:
- Never accept below your floor price.
- Reject if the buyer refuses to move above floor after several rounds.

Terms negotiation:
- Price is the primary lever. Be flexible on duration and access scope if price is right.
- If the buyer needs a longer duration, price it in proportionally.

Always respond with valid JSON only, no extra text:
{{"action": "offer|counter|accept|reject", "price": <float>, "terms": {{"access_scope": "<string>", "duration_days": <int>}}, "reasoning": "<string>"}}
"""

# Phase 6: appended to the seller system prompt when a DKIM email proof was
# verified inside the TEE.  The {domain} placeholder is filled at runtime.
# This credential gives the seller agent a verified organisational identity
# that it can reference in negotiation reasoning (e.g. "as a verified provider
# at acme.com I stand behind the data quality").
_MEMORY_BLOCK = """

[MEMORY CONTEXT — recalled from prior negotiations inside this TEE]
{memory_context}

Act on this. Adjust your opening ask and concession pace based on what you remember about this counterparty.
"""

_QUALITY_BLOCK = """

[TEE-VERIFIED DATASET QUALITY CREDENTIAL]
An independent DataQualityAgent assessed your dataset inside the TEE before negotiation began.
These findings are cryptographically attested and visible to the buyer.

{quality_context}

Be transparent about known issues. If quality is medium or low, consider proactively
acknowledging limitations and pricing them in rather than waiting for the buyer to raise them.
"""

_DKIM_CREDENTIAL_BLOCK = """

[TEE-VERIFIED IDENTITY CREDENTIAL]
Your identity as a representative of {domain} has been cryptographically verified
inside this Trusted Execution Environment via DKIM email proof prior to this
negotiation beginning.  You may reference this verified credential in your
negotiation reasoning.  This credential was established before any deal terms
were discussed and is immutable for the duration of this negotiation session.
"""


class SellerAgent:
    def __init__(
        self,
        floor_price: float,
        data_description: str,
        verified_domain: str | None = None,
        memory_context: str = "",
        quality_context: str = "",
    ):
        """
        Parameters
        ----------
        floor_price : float
            Minimum acceptable price; injected into the system prompt.
        data_description : str
            Description of the dataset being sold.
        verified_domain : str | None
            When provided, a TEE-verified DKIM credential for this domain is
            appended to the system prompt.  Should only be set when the DKIM
            verification in app/dkim/verifier.py returned verified=True.
        memory_context : str
            Recalled memories from prior negotiations, injected into the system
            prompt before negotiation starts.
        """
        self.floor_price = floor_price
        self.data_description = data_description
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = SELLER_SYSTEM_PROMPT.format(
            floor_price=floor_price,
            data_description=data_description,
        )
        if memory_context:
            self.system_prompt += _MEMORY_BLOCK.format(memory_context=memory_context)
        if quality_context:
            self.system_prompt += _QUALITY_BLOCK.format(quality_context=quality_context)
        if verified_domain:
            self.system_prompt += _DKIM_CREDENTIAL_BLOCK.format(domain=verified_domain)

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
            data, _ = json.JSONDecoder().raw_decode(raw, start)

        return {
            "action": data.get("action", "offer"),
            "price": float(data.get("price") or 0),
            "terms": data.get("terms", {}),
            "reasoning": data.get("reasoning", ""),
        }
