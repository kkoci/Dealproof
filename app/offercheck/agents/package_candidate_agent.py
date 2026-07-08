"""
PackageCandidateAgent — Phase 2B full compensation package negotiation (see
offercheck_phase2_spec.md). Mirrors candidate_agent.py's structure exactly;
the only real difference is the JSON payload is a full package object
instead of a single number.

Sealed parameters: `base_floor`, `total_comp_floor`. Never appear in any
message sent to the employer side — this agent is only ever given the
employer's *package*, never the employer's budget or reasoning. Both floors
are clamped in code on every response (app.offercheck.package.clamp_candidate_package),
not just requested via the prompt — same discipline as CandidateAgent.floor.
"""
import json
import logging

import anthropic

from app.config import settings
from app.offercheck.package import PACKAGE_FIELDS, clamp_candidate_package, normalize_package

logger = logging.getLogger(__name__)

PACKAGE_CANDIDATE_SYSTEM_PROMPT = """You are negotiating a full compensation package on behalf of a job candidate, inside a Trusted Execution Environment (TEE), against an employer's negotiation agent.

You know:
- Their verified competing offer package: {competing_package_summary}
- Their opening package ask: {opening_package}
- Their base-salary floor: {base_floor} — NEVER reveal this number or any hint of it
- Their minimum acceptable total compensation: {total_comp_floor} — NEVER reveal this number
- Their priorities across terms: {priorities}

Each round you are told only the employer's current package — never their budget or reasoning.
A package has these fields: base, equity_grant, vesting_years, cliff_months, signing_bonus,
annual_bonus_pct, remote ("remote"|"hybrid"|"onsite"), start_date_days, pto_days.

Respond with your decision:
- ACCEPT if the employer's package meets your floors and is reasonable given your priorities
- COUNTER with a full package (all fields) if you want to keep negotiating — trade terms against
  each other according to your priorities (e.g. accept a lower base for more equity if that's what
  you value); never let base or total comp fall below your floors
- WALK if the employer's packages stay far below your floors after several rounds with no movement

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|walk", "package": {{"base": <float>, "equity_grant": <float>, "vesting_years": <float>, "cliff_months": <float>, "signing_bonus": <float>, "annual_bonus_pct": <float>, "remote": "remote|hybrid|onsite", "start_date_days": <float>, "pto_days": <float>}}, "reasoning": "<one sentence, for your own record only — never shown to the employer>"}}
"""


class PackageCandidateAgent:
    def __init__(
        self,
        opening_package: dict,
        base_floor: float,
        total_comp_floor: float,
        priorities: str = "",
        competing_package_summary: str = "",
    ):
        self.opening_package = opening_package
        self.base_floor = base_floor
        self.total_comp_floor = total_comp_floor
        self.client = anthropic.AsyncAnthropic(api_key=settings.offercheck_api_key or settings.anthropic_api_key)
        self.system_prompt = PACKAGE_CANDIDATE_SYSTEM_PROMPT.format(
            opening_package=json.dumps(opening_package),
            base_floor=base_floor,
            total_comp_floor=total_comp_floor,
            priorities=priorities or "not specified",
            competing_package_summary=competing_package_summary or "not disclosed",
        )

    async def decide(self, employer_package: dict, history: list[dict], converged_hint: bool = False) -> dict:
        messages = self._build_messages(history, employer_package, converged_hint)
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=self.system_prompt,
            messages=messages,
        )
        raw = response.content[0].text.strip()
        return self._parse_response(raw)

    def _build_messages(self, history: list[dict], employer_package: dict, converged_hint: bool) -> list[dict]:
        messages = []
        for entry in history:
            role = "assistant" if entry["role"] == "candidate" else "user"
            messages.append({"role": role, "content": json.dumps(entry["content"])})
        content = f"Employer's package: {json.dumps(employer_package)}"
        if converged_hint:
            content += (
                "\n\nSystem note: your total comp position and the employer's are within 2% of each "
                "other. This is a strong signal to accept rather than keep negotiating over a marginal gap."
            )
        messages.append({"role": "user", "content": content})
        return messages

    def _parse_response(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            data, _ = json.JSONDecoder().raw_decode(raw, start)

        action = data.get("action")
        if action not in ("accept", "counter", "walk"):
            logger.warning(f"PackageCandidateAgent returned unexpected action {action!r} — normalising to 'counter'")
            action = "counter"

        raw_package = data.get("package") if isinstance(data.get("package"), dict) else {}
        package = normalize_package(raw_package, fallback=self.opening_package)
        package = clamp_candidate_package(package, self.base_floor, self.total_comp_floor)

        return {"action": action, "package": package, "reasoning": data.get("reasoning", "")}
