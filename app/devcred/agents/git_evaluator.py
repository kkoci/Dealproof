"""
GitEvaluatorAgent — LLM layer, runs after GitInspectorAgent.

Receives deterministic hard findings as grounding context.
Produces qualitative assessment and may adjust seniority_level upward
from the hard seniority_signal. Cannot downgrade below the hard finding.

The seniority floor is enforced in code — the LLM prompt also states this
explicitly so its text output is consistent with the clamped value.
"""
import json
import logging
from dataclasses import dataclass, field

import anthropic
from app.config import settings
from app.devcred.agents.git_inspector import GitInspectionReport, SENIORITY_ORDER

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior engineering credential evaluator inside an Intel TDX TEE.
You are assessing a developer's career trajectory from authenticated commit history.
Raw code is not visible — only commit metadata, diff statistics, and language distribution.

The hard findings below are deterministically computed from the commit corpus. They are authoritative.
You may provide qualitative context and adjust the seniority assessment upward if evidence supports it.
You may NOT downgrade seniority_level below the hard seniority_signal — if you attempt to, the system will clamp it.

Return ONLY valid JSON, no extra text:
{
  "seniority_level": "junior|mid|senior|staff",
  "primary_languages": ["Go", "Python"],
  "specializations": ["distributed systems", "API design"],
  "contribution_pattern": "<one sentence describing the pattern>",
  "qualitative_assessment": "<two to three sentences of qualitative analysis>",
  "confidence": "low|medium|high",
  "caveats": ["limited to N repos", "no test history visible"]
}

Confidence guide:
  high   — >= 200 commits across >= 2 years with file-level enrichment
  medium — 50-199 commits or 1-2 years
  low    — < 50 commits or < 1 year or significant gaps in metrics"""

_USER_TEMPLATE = """Hard findings (deterministic, authoritative):
{hard_findings}

Raw metrics:
{metrics}

Hard seniority_signal: {seniority_signal}
You may set seniority_level to "{seniority_signal}" or higher. Do not set it lower.

Produce the credential evaluation JSON."""


@dataclass
class GitEvaluation:
    seniority_level: str       # >= hard seniority_signal (enforced in code)
    primary_languages: list[str]
    specializations: list[str]
    contribution_pattern: str
    qualitative_assessment: str
    confidence: str            # "low" | "medium" | "high"
    caveats: list[str]


def _clamp_seniority(hard: str, proposed: str) -> str:
    """Ensure proposed seniority is not below the hard finding."""
    hard_idx = SENIORITY_ORDER.index(hard) if hard in SENIORITY_ORDER else 0
    prop_idx = SENIORITY_ORDER.index(proposed) if proposed in SENIORITY_ORDER else 0
    return SENIORITY_ORDER[max(hard_idx, prop_idx)]


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start == -1:
            raise
        data, _ = json.JSONDecoder().raw_decode(raw, start)
        return data


class GitEvaluatorAgent:
    """
    LLM layer. Runs after GitInspectorAgent.
    Hard findings from GitInspectorAgent are injected as grounding context.
    seniority_level is clamped to >= hard seniority_signal regardless of LLM output.
    """

    def __init__(self) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def evaluate(
        self,
        metrics: dict,
        hard_findings: GitInspectionReport,
    ) -> GitEvaluation | None:
        """
        Produce a qualitative credential evaluation grounded in hard findings.
        Returns None on failure — non-fatal, caller decides how to proceed.
        """
        hard_dict = {
            "years_active": hard_findings.years_active,
            "languages_deep": hard_findings.languages_deep,
            "has_test_culture": hard_findings.has_test_culture,
            "consistent_contribution": hard_findings.consistent_contribution,
            "avg_commit_quality": hard_findings.avg_commit_quality,
            "seniority_signal": hard_findings.seniority_signal,
        }

        prompt = _USER_TEMPLATE.format(
            hard_findings=json.dumps(hard_dict, indent=2),
            metrics=json.dumps(
                {k: v for k, v in metrics.items() if k != "files"},
                indent=2,
            ),
            seniority_signal=hard_findings.seniority_signal,
        )

        try:
            response = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=768,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()
            data = _extract_json(raw)

            proposed = str(data.get("seniority_level", hard_findings.seniority_signal))
            clamped = _clamp_seniority(hard_findings.seniority_signal, proposed)

            if clamped != proposed:
                logger.warning(
                    "GitEvaluatorAgent: LLM proposed seniority_level=%r below hard signal=%r "
                    "— clamped to %r",
                    proposed,
                    hard_findings.seniority_signal,
                    clamped,
                )

            return GitEvaluation(
                seniority_level=clamped,
                primary_languages=data.get("primary_languages") or [],
                specializations=data.get("specializations") or [],
                contribution_pattern=str(data.get("contribution_pattern", "")),
                qualitative_assessment=str(data.get("qualitative_assessment", "")),
                confidence=str(data.get("confidence", "low")),
                caveats=data.get("caveats") or [],
            )

        except Exception as exc:
            logger.warning(
                "GitEvaluatorAgent.evaluate failed — %s: %s", type(exc).__name__, exc
            )
            return None
