"""
InvestorAgent — fundraising negotiation counterpart to BuyerAgent.

Mirrors app/agents/buyer.py exactly in structure (same method signatures,
same JSON response schema, same memory block pattern) so that run_negotiation()
from app/agents/negotiation.py can use InvestorAgent in place of BuyerAgent
without any modification to the loop.

The investor evaluates offers against a maximum valuation cap (= budget in
Deal Room vocabulary) and its desired ownership / investment parameters.
The FundraisingDiligenceCredential (ratios-only, no raw founder data) is
injected as grounding so the investor's position is anchored to attested figures.
"""
import json
import anthropic
from app.config import settings

_MEMORY_BLOCK = """

[MEMORY CONTEXT — recalled from prior fundraising rounds inside this TEE]
{memory_context}

Act on this. Adjust your opening offer and concession pace based on what
you remember about this founder. A founder who previously held firm near
their ask should get a higher opening offer to avoid wasted rounds.
"""

_DILIGENCE_BLOCK = """

[TEE-VERIFIED DILIGENCE CREDENTIAL — ratios only, no raw data]
The following metric ratios were computed and attested inside the TEE from
the founder's submitted financial data. You have not seen the underlying
figures — only these derived ratios. Use them to calibrate your offer.

{diligence_summary}

Your valuation offer should reflect this evidence. If flags are raised,
justify a lower offer. If metrics are strong, acknowledge them.
"""

INVESTOR_SYSTEM_PROMPT = """You are a venture capital investor agent negotiating pre-money valuation with a startup founder inside a Trusted Execution Environment (TEE).

Your goal: invest at the lowest pre-money valuation that represents fair value given the company's metrics.

Maximum acceptable pre-money valuation (hard cap — never offer above this): {max_valuation}
Target investment amount: {investment_amount}
Target ownership percentage: {target_ownership_pct}%
Your investment thesis / requirements: {requirements}

Use your judgment to negotiate. Open lower than your cap, concede gradually based on the
founder's metric-grounded arguments. If the founder claims metrics that appear inconsistent
with the attested diligence findings, challenge them.

Hard constraints:
- Never offer above your maximum valuation cap.
- Walk away if the founder refuses to come below your cap after several rounds.

Terms alongside valuation:
- Ownership percentage and pro-rata rights matter — if valuation is near your cap,
  push for better terms to compensate.

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|reject", "price": <float>, "terms": {{"ownership_pct": <float>, "investment_amount": <float>, "notes": "<string>"}}, "reasoning": "<string>"}}
"""


class InvestorAgent:
    """
    Negotiates pre-money valuation on behalf of a VC investor.

    Drop-in replacement for BuyerAgent in run_negotiation():
      - .budget          → maximum acceptable valuation (used by ArbitratorAgent)
      - .evaluate_offer(founder_offer, history) → same signature as BuyerAgent.evaluate_offer()
    """

    def __init__(
        self,
        max_valuation: float,
        investment_amount: float,
        target_ownership_pct: float,
        requirements: str = "",
        diligence_summary: str = "",
        memory_context: str = "",
    ):
        """
        Parameters
        ----------
        max_valuation : float
            Hard cap on pre-money valuation. Exposed as .budget for
            compatibility with run_negotiation() / ArbitratorAgent.
        investment_amount : float
            Amount the investor wants to deploy (informs ownership calculations).
        target_ownership_pct : float
            Desired equity stake as a percentage (e.g. 15.0 = 15%).
        requirements : str
            Investment thesis / deal requirements.
        diligence_summary : str
            Formatted ratios from FundraisingDiligenceCredential (no raw data).
        memory_context : str
            Recalled memories from prior negotiations via Contexto sidecar.
        """
        self.budget = max_valuation             # negotiation.py / arbitrator compatibility
        self.max_valuation = max_valuation
        self.investment_amount = investment_amount
        self.target_ownership_pct = target_ownership_pct
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        self.system_prompt = INVESTOR_SYSTEM_PROMPT.format(
            max_valuation=max_valuation,
            investment_amount=investment_amount,
            target_ownership_pct=target_ownership_pct,
            requirements=requirements or "Strong metrics, experienced team, large market.",
        )
        if diligence_summary:
            self.system_prompt += _DILIGENCE_BLOCK.format(diligence_summary=diligence_summary)
        if memory_context:
            self.system_prompt += _MEMORY_BLOCK.format(memory_context=memory_context)

    async def evaluate_offer(self, founder_offer: dict, history: list[dict]) -> dict:
        """Mirror BuyerAgent.evaluate_offer() — same signature, used by run_negotiation()."""
        messages = self._build_messages(history, founder_offer)

        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=self.system_prompt,
            messages=messages,
        )

        raw = response.content[0].text.strip()
        return self._parse_response(raw)

    def _build_messages(self, history: list[dict], current_offer: dict) -> list[dict]:
        messages = []
        for entry in history:
            # seller = founder → user turn for investor
            role = "user" if entry["role"] == "seller" else "assistant"
            messages.append({"role": role, "content": json.dumps(entry["content"])})
        messages.append({"role": "user", "content": f"Founder's offer: {json.dumps(current_offer)}"})
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
            "terms": data.get("terms", {}),
            "reasoning": data.get("reasoning", ""),
        }
