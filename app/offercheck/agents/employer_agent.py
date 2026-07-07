"""
EmployerAgent — autoplay negotiation (see app/agents/seller.py, which this
mirrors: hard band clamp enforced in code, same client/response contract).

Privacy: only ever given round number, gap_pct, the candidate's last move,
and its own current offer. Never handed the candidate's raw ask or
competing-offer details.
"""
import json
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

EMPLOYER_SYSTEM_PROMPT = """You are a talent-acquisition negotiation agent representing the employer, negotiating a salary offer against a candidate inside a Trusted Execution Environment (TEE).

Your goal: land the candidate at a fair price without exceeding your band.

Salary band for this role — minimum {band_min}, midpoint {band_mid}, maximum {band_max} (hard ceiling, never exceed it).
Prefer to land at or below the midpoint when the candidate will accept it.

You do NOT see the candidate's raw ask or their competing offer details. Each round you are only told:
- the round number and how many rounds remain
- the current gap percentage between the candidate's ask and your position (positive = they're above you)
- the candidate's last move (accept / counter / walk)

Hard constraints:
- Never offer above your band maximum.
- Accept once the candidate's ask is close enough to your band to be worth taking rather than risking more rounds.
- Walk away if the candidate stays far above your band after several rounds with no meaningful movement.

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|walk", "value": <float — your new offer if countering>, "reasoning": "<one sentence>"}}
"""


class EmployerAgent:
    def __init__(self, band_min: float, band_mid: float, band_max: float):
        self.band_min = band_min
        self.band_mid = band_mid
        self.band_max = band_max
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = EMPLOYER_SYSTEM_PROMPT.format(band_min=band_min, band_mid=band_mid, band_max=band_max)

    async def decide(
        self,
        round_number: int,
        max_rounds: int,
        my_current_value: float | None,
        gap_pct: float | None,
        last_candidate_move: str | None,
        history: list[dict],
    ) -> dict:
        prompt = self._build_prompt(round_number, max_rounds, my_current_value, gap_pct, last_candidate_move, history)
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=384,
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        fallback = my_current_value if my_current_value is not None else self.band_mid
        return self._parse_response(raw, fallback)

    def _build_prompt(
        self,
        round_number: int,
        max_rounds: int,
        my_current_value: float | None,
        gap_pct: float | None,
        last_candidate_move: str | None,
        history: list[dict],
    ) -> str:
        history_lines = "\n".join(f"Round {h['round']}: {h['actor']} {h['move']}" for h in history) or "No moves yet."
        gap_line = f"{gap_pct:+.1f}%" if gap_pct is not None else "not yet known (this is your first move)"
        current_line = f"{my_current_value}" if my_current_value is not None else "not yet made — this is your opening move"
        return (
            f"Round {round_number} of {max_rounds} max.\n"
            f"Your current offer: {current_line}\n"
            f"Gap to candidate's ask: {gap_line}\n"
            f"Candidate's last move: {last_candidate_move or 'none yet'}\n"
            f"History:\n{history_lines}\n\n"
            "Decide your move."
        )

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
