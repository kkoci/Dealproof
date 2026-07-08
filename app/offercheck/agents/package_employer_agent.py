"""
PackageEmployerAgent — Phase 2B full compensation package negotiation (see
offercheck_phase2_spec.md). Mirrors employer_agent.py's structure exactly;
mirrors package_candidate_agent.py's package-shaped I/O.

Sealed parameters: `base_min`/`base_max`, `total_comp_budget`. Never appear
in any message sent to the candidate side. Both are clamped in code on every
response (app.offercheck.package.clamp_employer_package), not just requested
via the prompt.
"""
import json
import logging

import anthropic

from app.config import settings
from app.offercheck.package import clamp_employer_package, normalize_package

logger = logging.getLogger(__name__)

PACKAGE_EMPLOYER_SYSTEM_PROMPT = """You are negotiating a full compensation package on behalf of an employer, inside a Trusted Execution Environment (TEE), against a candidate's negotiation agent.

You know:
- Your base salary range for this role: minimum {base_min}, maximum {base_max} — NEVER reveal these numbers, and never exceed the maximum
- Your total compensation budget across all terms: {total_comp_budget} — NEVER reveal this number
- Your flexibility across terms: {priorities}

Each round you are told only the candidate's current package — never their floors or reasoning.
A package has these fields: base, equity_grant, vesting_years, cliff_months, signing_bonus,
annual_bonus_pct, remote ("remote"|"hybrid"|"onsite"), start_date_days, pto_days.

Respond with your decision:
- ACCEPT if the candidate's package is within your budget and reasonable
- COUNTER with a full package (all fields) if you want to keep negotiating — trade terms against
  your stated flexibility (e.g. stretch on signing bonus while holding base firm); never let base
  exceed your maximum or total comp exceed your budget
- WALK if the candidate stays far above your budget after several rounds with no movement

Always respond with valid JSON only, no extra text:
{{"action": "accept|counter|walk", "package": {{"base": <float>, "equity_grant": <float>, "vesting_years": <float>, "cliff_months": <float>, "signing_bonus": <float>, "annual_bonus_pct": <float>, "remote": "remote|hybrid|onsite", "start_date_days": <float>, "pto_days": <float>}}, "reasoning": "<one sentence, for your own record only — never shown to the candidate>"}}
"""


class PackageEmployerAgent:
    def __init__(
        self,
        base_min: float,
        base_max: float,
        total_comp_budget: float,
        priorities: str = "",
        opening_package: dict | None = None,
    ):
        self.base_min = base_min
        self.base_max = base_max
        self.total_comp_budget = total_comp_budget
        # Fallback shape for normalize_package when the LLM omits fields on its opening move.
        self.opening_package = opening_package or {
            "base": base_min, "equity_grant": 0, "vesting_years": 4, "cliff_months": 12,
            "signing_bonus": 0, "annual_bonus_pct": 0, "remote": "hybrid", "start_date_days": 30, "pto_days": 15,
        }
        self.client = anthropic.AsyncAnthropic(api_key=settings.offercheck_api_key or settings.anthropic_api_key)
        self.system_prompt = PACKAGE_EMPLOYER_SYSTEM_PROMPT.format(
            base_min=base_min,
            base_max=base_max,
            total_comp_budget=total_comp_budget,
            priorities=priorities or "not specified",
        )

    async def decide(self, candidate_package: dict, history: list[dict], converged_hint: bool = False) -> dict:
        messages = self._build_messages(history, candidate_package, converged_hint)
        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=self.system_prompt,
            messages=messages,
        )
        raw = response.content[0].text.strip()
        return self._parse_response(raw)

    def _build_messages(self, history: list[dict], candidate_package: dict, converged_hint: bool) -> list[dict]:
        messages = []
        for entry in history:
            role = "assistant" if entry["role"] == "employer" else "user"
            messages.append({"role": role, "content": json.dumps(entry["content"])})
        content = f"Candidate's package: {json.dumps(candidate_package)}"
        if converged_hint:
            content += (
                "\n\nSystem note: your total comp position and the candidate's are within 2% of each "
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
            logger.warning(f"PackageEmployerAgent returned unexpected action {action!r} — normalising to 'counter'")
            action = "counter"

        raw_package = data.get("package") if isinstance(data.get("package"), dict) else {}
        package = normalize_package(raw_package, fallback=self.opening_package)
        package = clamp_employer_package(package, self.base_min, self.base_max, self.total_comp_budget)

        return {"action": action, "package": package, "reasoning": data.get("reasoning", "")}
