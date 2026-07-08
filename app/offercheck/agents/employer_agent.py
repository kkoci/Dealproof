"""
EmployerAgent — Phase 2A agentic negotiation (see offercheck_phase2_spec.md
and app/agents/seller.py, which this mirrors).

Sealed parameters: `band_min`/`band_mid`/`band_max` (clamped by the caller's
authority_limit — see mediator.py). Never appear in any message sent to the
candidate side — this agent is only ever given the candidate's offer amount.
Band is clamped in code on every response, not just requested via the
prompt, same as CandidateAgent's floor.
"""
import json
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

EMPLOYER_SYSTEM_PROMPT = """You are negotiating a salary offer on behalf of an employer, inside a Trusted Execution Environment (TEE), against a candidate's negotiation agent.

You know:
- Your salary band for this role: minimum {band_min}, midpoint {band_mid}, maximum {band_max} — NEVER reveal these numbers, and never exceed the maximum
- Your priorities: {priorities}

Each round you are told only the candidate's current ask — never their walk-away floor or reasoning. Respond with your decision:
- ACCEPT if the ask is within your band and justified
- COUNTER with a new offer if you want to keep negotiating (never exceed your band maximum)
- WALK if the candidate stays too far above your band after several rounds with no meaningful movement

Prefer to land at or below the midpoint when the candidate will accept it.

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|walk", "value": <float — your new offer if countering>, "reasoning": "<one sentence, for your own record only — never shown to the candidate>"}}
"""


class EmployerAgent:
    def __init__(self, band_min: float, band_mid: float, band_max: float, priorities: str = ""):
        self.band_min = band_min
        self.band_mid = band_mid
        self.band_max = band_max
        self.client = anthropic.AsyncAnthropic(api_key=settings.offercheck_api_key or settings.anthropic_api_key)
        self.system_prompt = EMPLOYER_SYSTEM_PROMPT.format(
            band_min=band_min,
            band_mid=band_mid,
            band_max=band_max,
            priorities=priorities or "not specified",
        )

    async def decide(self, candidate_ask: float, history: list[dict]) -> dict:
        """
        history: this agent's own private conversation log, built by the
        mediator — its own past turns in full (including reasoning), the
        candidate's past turns stripped to {action, value} only.
        """
        messages = self._build_messages(history, candidate_ask)
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=384,
            system=self.system_prompt,
            messages=messages,
        )
        raw = response.content[0].text.strip()
        return self._parse_response(raw, fallback_value=self.band_mid)

    def _build_messages(self, history: list[dict], candidate_ask: float) -> list[dict]:
        messages = []
        for entry in history:
            role = "assistant" if entry["role"] == "employer" else "user"
            messages.append({"role": role, "content": json.dumps(entry["content"])})
        messages.append({"role": "user", "content": f"Candidate's ask: {candidate_ask}"})
        return messages

    def _parse_response(self, raw: str, fallback_value: float) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            data, _ = json.JSONDecoder().raw_decode(raw, start)

        action = data.get("action")
        if action not in ("accept", "counter", "walk"):
            logger.warning(f"EmployerAgent returned unexpected action {action!r} — normalising to 'counter'")
            action = "counter"

        raw_value = data.get("value")
        try:
            value = float(raw_value) if raw_value not in (None, "") else fallback_value
        except (TypeError, ValueError):
            value = fallback_value

        # Hard band clamp enforced in code — the prompt asks nicely, this guarantees it.
        value = max(self.band_min, min(self.band_max, value))

        return {"action": action, "value": value, "reasoning": data.get("reasoning", "")}
