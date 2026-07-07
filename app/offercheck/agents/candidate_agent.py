"""
CandidateAgent — autoplay negotiation (see app/agents/buyer.py, which this
mirrors deliberately: same client setup, same JSON-response contract, same
"hard constraint enforced in code, not just the prompt" discipline).

Added on top of build_spec_offer_check.md at explicit user request: the
build spec never calls for agentic negotiation in this vertical (Phase 1 says
"no LLM" outright), but core DealProof's whole premise is two agents
negotiating inside a TEE — a human-only revision loop doesn't resemble that.

Privacy: this agent is only ever given what a human candidate would see in
the real flow — round number, gap_pct, the employer's last move, and its own
current ask. It is never handed the employer's raw band or offer value.
"""
import json
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

CANDIDATE_SYSTEM_PROMPT = """You are a job candidate's negotiation agent, negotiating your own salary ask against an employer inside a Trusted Execution Environment (TEE).

Your goal: land the highest salary you can without ever asking for less than your minimum acceptable number.

Minimum acceptable ask (hard floor — never counter below this): {min_acceptable}
Your opening ask: {opening_ask}
Context on your competing offer: {competing_offer_summary}

You do NOT see the employer's salary band or their raw offer. Each round you are only told:
- the round number and how many rounds remain
- the current gap percentage between your ask and the employer's position (positive = you're asking above them)
- the employer's last move (accept / counter / walk)

Negotiate using the gap trend across rounds — if the gap is shrinking, the employer is moving toward
you; concede more slowly than they do. Give ground in smaller steps as the gap narrows.

Hard constraints:
- Never counter with a value below your minimum acceptable ask.
- Accept once the employer's position is close enough to be worth taking rather than risking more rounds.
- Walk away if the employer's offers stay far below your minimum after several rounds with no meaningful movement.

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|walk", "value": <float — your new ask if countering>, "reasoning": "<one sentence>"}}
"""


class CandidateAgent:
    def __init__(self, opening_ask: float, min_acceptable: float, competing_offer_summary: str = ""):
        self.opening_ask = opening_ask
        self.min_acceptable = min_acceptable
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = CANDIDATE_SYSTEM_PROMPT.format(
            min_acceptable=min_acceptable,
            opening_ask=opening_ask,
            competing_offer_summary=competing_offer_summary or "not disclosed",
        )

    async def decide(
        self,
        round_number: int,
        max_rounds: int,
        my_current_value: float,
        gap_pct: float | None,
        last_employer_move: str | None,
        history: list[dict],
    ) -> dict:
        prompt = self._build_prompt(round_number, max_rounds, my_current_value, gap_pct, last_employer_move, history)
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=384,
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        return self._parse_response(raw, my_current_value)

    def _build_prompt(
        self,
        round_number: int,
        max_rounds: int,
        my_current_value: float,
        gap_pct: float | None,
        last_employer_move: str | None,
        history: list[dict],
    ) -> str:
        history_lines = "\n".join(f"Round {h['round']}: {h['actor']} {h['move']}" for h in history) or "No moves yet."
        gap_line = f"{gap_pct:+.1f}%" if gap_pct is not None else "not yet known (employer hasn't moved)"
        return (
            f"Round {round_number} of {max_rounds} max.\n"
            f"Your current ask: {my_current_value}\n"
            f"Gap to employer's position: {gap_line}\n"
            f"Employer's last move: {last_employer_move or 'none yet'}\n"
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
            logger.warning(f"CandidateAgent returned unexpected action {action!r} — normalising to 'counter'")
            action = "counter"

        raw_value = data.get("value")
        try:
            value = float(raw_value) if raw_value not in (None, "") else fallback_value
        except (TypeError, ValueError):
            value = fallback_value

        # Hard floor enforced in code — the prompt asks nicely, this guarantees it.
        if value < self.min_acceptable:
            value = self.min_acceptable

        return {"action": action, "value": value, "reasoning": data.get("reasoning", "")}
