"""
GitEvaluatorAgent — LLM qualitative layer.

Runs after GitInspectorAgent. Receives hard metrics and findings as grounding.
Can adjust seniority_signal upward based on qualitative evidence.
Cannot move seniority_signal downward from the hard finding.
"""
import json
import logging
import anthropic

from app.config import settings
from app.devcred.agents.git_inspector import GitInspectionReport

logger = logging.getLogger(__name__)

_SENIORITY_ORDER = ["junior", "mid", "senior", "staff"]

_SYSTEM_PROMPT = (
    "You are a senior engineering credential evaluator inside an Intel TDX "
    "Trusted Execution Environment. You are assessing a developer's career "
    "trajectory from authenticated commit history. Raw code is not visible — "
    "only commit metadata, diff statistics, and language distribution.\n\n"
    "The hard findings below are deterministically computed from authenticated "
    "git data and are authoritative. You may provide qualitative context and "
    "adjust the seniority assessment UPWARD if the evidence clearly supports it. "
    "You may NOT downgrade the seniority_level below the hard finding.\n\n"
    "Return ONLY valid JSON matching this exact shape:\n"
    '{\n'
    '  "seniority_level": "junior|mid|senior|staff",\n'
    '  "primary_languages": ["Go", "Python"],\n'
    '  "specializations": ["distributed systems", "API design"],\n'
    '  "contribution_pattern": "<one sentence describing commit pattern>",\n'
    '  "qualitative_assessment": "<two to three sentences>",\n'
    '  "confidence": "low|medium|high",\n'
    '  "caveats": ["limited to 2 repos", "no test history visible"]\n'
    "}"
)


class GitEvaluatorAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def evaluate(
        self,
        metrics: dict,
        inspection: GitInspectionReport,
        developer_handle: str,
    ) -> dict | None:
        hard_findings_block = json.dumps(
            {
                "years_active": inspection.years_active,
                "languages_deep": inspection.languages_deep,
                "has_test_culture": inspection.has_test_culture,
                "consistent_contribution": inspection.consistent_contribution,
                "avg_commit_quality": inspection.avg_commit_quality,
                "hard_seniority_signal": inspection.seniority_signal,
                "total_commits": metrics.get("total_commits"),
                "active_months": metrics.get("active_months"),
                "languages": metrics.get("languages"),
                "test_file_ratio": round(metrics.get("test_file_ratio", 0.0), 3),
                "avg_diff_size": round(metrics.get("avg_diff_size", 0.0), 1),
            },
            indent=2,
        )

        user_message = (
            f"Developer: {developer_handle}\n\n"
            f"HARD FINDINGS (authoritative — do not contradict):\n"
            f"{hard_findings_block}\n\n"
            f"Provide your qualitative engineering credential assessment. "
            f"Your seniority_level must be >= '{inspection.seniority_signal}'."
        )

        try:
            response = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=768,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw = response.content[0].text.strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                start = raw.find("{")
                data, _ = json.JSONDecoder().raw_decode(raw, start)

            # Enforce seniority floor — LLM cannot downgrade below hard finding
            llm_level = data.get("seniority_level", inspection.seniority_signal)
            hard_idx = (
                _SENIORITY_ORDER.index(inspection.seniority_signal)
                if inspection.seniority_signal in _SENIORITY_ORDER
                else 0
            )
            llm_idx = (
                _SENIORITY_ORDER.index(llm_level)
                if llm_level in _SENIORITY_ORDER
                else 0
            )
            data["seniority_level"] = _SENIORITY_ORDER[max(hard_idx, llm_idx)]

            return data

        except Exception as exc:
            logger.warning(
                f"GitEvaluatorAgent: evaluation failed — {type(exc).__name__}: {exc}"
            )
            return None
