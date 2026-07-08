"""
CandidateAgent — Phase 2A agentic negotiation (see offercheck_phase2_spec.md
and app/agents/buyer.py, which this deliberately mirrors: AsyncAnthropic
client setup, JSON response contract, multi-turn message history so the
agent "remembers" its own prior reasoning across rounds).

Sealed parameter: `floor`. Never appears in any message sent to the employer
side — enforced by app.offercheck.agents.mediator, which only ever gives this
agent the employer's *offer amount*, never the employer's band or reasoning.
The floor is also clamped in code on every response, not just requested via
the prompt — same "hard constraint enforced in code" discipline as core's
BuyerAgent.budget / SellerAgent.floor_price.
"""
import json
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

CANDIDATE_SYSTEM_PROMPT = """You are negotiating a salary on behalf of a job candidate, inside a Trusted Execution Environment (TEE), against an employer's negotiation agent.

You know:
- Their verified competing offer: {competing_offer_summary}
- Their opening ask at the target employer: {opening_ask}
- Their walk-away floor: {floor} — NEVER reveal this number or any hint of it in your response
- Their priorities: {priorities}

Each round you are told only the employer's current offer amount — never the employer's band, budget, or reasoning. Respond with your decision:
- ACCEPT if the offer meets or exceeds your floor and is reasonable given your priorities
- COUNTER with a new ask if you want to keep negotiating (never go below your floor)
- WALK if the employer stays too far below your floor after several rounds with no meaningful movement

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|walk", "value": <float — your new ask if countering>, "reasoning": "<one sentence, for your own record only — never shown to the employer>"}}
"""


class CandidateAgent:
    def __init__(self, opening_ask: float, floor: float, priorities: str = "", competing_offer_summary: str = ""):
        self.opening_ask = opening_ask
        self.floor = floor
        self.client = anthropic.AsyncAnthropic(api_key=settings.offercheck_api_key or settings.anthropic_api_key)
        self.system_prompt = CANDIDATE_SYSTEM_PROMPT.format(
            opening_ask=opening_ask,
            floor=floor,
            priorities=priorities or "not specified",
            competing_offer_summary=competing_offer_summary or "not disclosed",
        )

    async def decide(self, employer_offer: float, history: list[dict]) -> dict:
        """
        history: this agent's own private conversation log, built by the
        mediator — its own past turns in full (including reasoning), the
        employer's past turns stripped to {action, value} only.
        """
        messages = self._build_messages(history, employer_offer)
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=384,
            system=self.system_prompt,
            messages=messages,
        )
        raw = response.content[0].text.strip()
        return self._parse_response(raw, fallback_value=self.opening_ask)

    def _build_messages(self, history: list[dict], employer_offer: float) -> list[dict]:
        messages = []
        for entry in history:
            role = "assistant" if entry["role"] == "candidate" else "user"
            messages.append({"role": role, "content": json.dumps(entry["content"])})
        messages.append({"role": "user", "content": f"Employer's offer: {employer_offer}"})
        return messages

    def _parse_response(self, raw: str, fallback_value: float) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            data, _ = json.JSONDecoder().raw_decode(raw, start)

        action = data.get("action")
        if action not in ("accept", "counter", "walk"):
            logger.warning(f"CandidateAgent returned unexpected action {action!r} — normalising to 'counter'")
            action = "counter"

        raw_value = data.get("value")
        try:
            value = float(raw_value) if raw_value not in (None, "") else fallback_value
        except (TypeError, ValueError):
            value = fallback_value

        # Hard floor enforced in code — the prompt asks nicely, this guarantees it.
        if value < self.floor:
            value = self.floor

        return {"action": action, "value": value, "reasoning": data.get("reasoning", "")}
