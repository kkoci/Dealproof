"""
MetricsEvaluatorAgent — LLM qualitative layer (Phase 2).

Runs after MetricsInspectorAgent. Receives hard findings as grounding.
Cannot contradict hard findings — they are passed directly in the prompt
and the response schema enforces it.

Mirrors AuditorAgent in app/agents/auditor.py:
  one Claude call → structured JSON → dataclass result → non-fatal on failure
"""
import json
import hashlib
import logging
import anthropic
from dataclasses import dataclass, field

from app.config import settings
from app.fundraising.agents.metrics_inspector import MetricsInspectionReport

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a fundraising due-diligence evaluator running inside an Intel TDX \
Trusted Execution Environment. You are assessing a company's financial metrics for an investor, \
based on authenticated structured data the investor will never see directly.

The hard findings below are deterministically computed from the company's actual financial records \
and are authoritative. Your role is to provide qualitative context, flag notable patterns, and \
surface caveats — not to override or contradict the hard findings.

Be conservative and precise. This credential will be relied upon by an investor making a funding \
decision. Do not editorialize or speculate beyond what the evidence supports.

Return ONLY valid JSON matching this exact shape:
{
  "metric_assessments": [
    {
      "metric": "<metric_name>",
      "hard_finding": {},
      "qualitative_assessment": "<one concise sentence>",
      "caveats": []
    }
  ],
  "overall_assessment": "<two to three sentences>",
  "notable_strengths": ["<string>"],
  "notable_risks": ["<string>"]
}"""


@dataclass
class MetricAssessment:
    metric: str
    hard_finding: dict
    qualitative_assessment: str
    caveats: list[str] = field(default_factory=list)


@dataclass
class EvaluationReport:
    metric_assessments: list[MetricAssessment]
    overall_assessment: str
    notable_strengths: list[str]
    notable_risks: list[str]
    evaluation_hash: str  # SHA-256(canonical fields) — in TDX report_data (Phase 3)


class MetricsEvaluatorAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    def _build_hard_findings_block(
        self,
        metric_evidence: dict,
        inspection: MetricsInspectionReport,
    ) -> str:
        """Serialise hard findings into a prompt-readable block."""
        findings = {
            "mom_growth": {
                "computed_rate": inspection.mom_growth_computed,
                "verified_vs_claim": inspection.mom_growth_verified,
            },
            "customer_concentration": {
                "top_customer_pct": inspection.top_customer_pct,
                "concentration_flagged": inspection.customer_concentration_flag,
            },
            "gross_margin": {
                "computed_pct": inspection.gross_margin_computed,
                "verified_vs_claim": inspection.gross_margin_verified,
            },
            "burn_rate": {
                "runway_months": inspection.runway_months_computed,
                "runway_flagged": inspection.runway_flag,
                "monthly_burn": metric_evidence.get("burn_rate", {}).get("monthly_burn"),
                "cash_balance": metric_evidence.get("burn_rate", {}).get("cash_balance"),
            },
            "churn_rate": {
                "computed_monthly_churn": inspection.churn_rate_computed,
                "churn_flagged": inspection.churn_flag,
            },
            "arr_consistency": {
                "arr_delta_pct": inspection.arr_delta_pct,
                "arr_verified": inspection.arr_consistency_verified,
                "computed_arr": metric_evidence.get("arr_consistency", {}).get("computed_arr"),
                "reported_arr": metric_evidence.get("arr_consistency", {}).get("reported_arr"),
            },
        }
        return json.dumps(findings, indent=2)

    async def evaluate(
        self,
        metric_evidence: dict,
        inspection: MetricsInspectionReport,
        company_name: str,
        round_label: str | None = None,
    ) -> EvaluationReport | None:
        hard_findings_block = self._build_hard_findings_block(metric_evidence, inspection)
        round_str = f" ({round_label})" if round_label else ""

        user_message = (
            f"Company: {company_name}{round_str}\n\n"
            f"HARD FINDINGS (authoritative — do not contradict):\n"
            f"{hard_findings_block}\n\n"
            f"Provide your qualitative due-diligence assessment."
        )

        try:
            response = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw = response.content[0].text.strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                start = raw.find("{")
                data, _ = json.JSONDecoder().raw_decode(raw, start)

            assessments = [
                MetricAssessment(
                    metric=a.get("metric", ""),
                    hard_finding=a.get("hard_finding", {}),
                    qualitative_assessment=a.get("qualitative_assessment", ""),
                    caveats=a.get("caveats", []),
                )
                for a in data.get("metric_assessments", [])
            ]

            fields = {
                "overall_assessment": data.get("overall_assessment", ""),
                "notable_strengths": data.get("notable_strengths", []),
                "notable_risks": data.get("notable_risks", []),
                "any_flag_raised": inspection.any_flag_raised,
            }
            evaluation_hash = hashlib.sha256(
                json.dumps(fields, sort_keys=True).encode()
            ).hexdigest()

            return EvaluationReport(
                metric_assessments=assessments,
                overall_assessment=fields["overall_assessment"],
                notable_strengths=fields["notable_strengths"],
                notable_risks=fields["notable_risks"],
                evaluation_hash=evaluation_hash,
            )

        except Exception as exc:
            logger.warning(
                f"MetricsEvaluatorAgent: evaluation failed — {type(exc).__name__}: {exc}"
            )
            raise
