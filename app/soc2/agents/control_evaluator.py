"""
ControlEvaluatorAgent — LLM qualitative layer for SOC 2 controls.

Mirrors app/agents/auditor.py exactly:
- Runs AFTER ConfigInspectorAgent.
- Receives hard findings as established facts — cannot override them.
- Adds qualitative context, risk notes, and edge-case flagging only.
- Returns ControlEvaluation (hard booleans overwritten from inspector results).
"""
import hashlib
import json
import logging
import anthropic
from dataclasses import dataclass, field

from app.config import settings
from app.soc2.agents.config_inspector import ControlCheckResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a SOC 2 compliance evaluator inside an Intel TDX Trusted Execution Environment.

The hard findings below are deterministically computed and authoritative — they were produced by a rule-based inspector that reads the actual config values. Your role is qualitative context and edge-case flagging only. Do NOT override or contradict hard findings.

Hard findings are labeled PASS or FAIL. Your qualitative_assessment and risk_notes should add context that a human auditor would find useful, such as: compensating controls, residual risk even when passing, remediation advice when failing, or caveats about the evidence quality.

Return ONLY valid JSON — no explanation, no markdown, no code fences:
{
  "control_assessments": [
    {
      "control_id": "CC6.1",
      "hard_finding": true,
      "qualitative_assessment": "one or two sentences of qualitative context",
      "risk_notes": "any residual risk or caveats",
      "effective": true
    }
  ],
  "overall_assessment": "one paragraph summarising the organisation's SOC 2 posture across all six controls",
  "material_weaknesses": ["list of control_ids with critical failures, or empty list"],
  "significant_deficiencies": ["list of control_ids with moderate concerns, or empty list"]
}

The effective field in your response MUST match the hard_finding boolean — do not set effective=true when hard_finding=false, or vice versa."""

_USER_TEMPLATE = """Organisation: {org_name}

Hard findings from deterministic inspection:
{hard_findings_block}

Config evidence summary:
{evidence_block}

Provide qualitative assessment for each control and an overall posture summary."""


@dataclass
class ControlEvaluation:
    control_assessments: list[dict]
    overall_assessment: str
    material_weaknesses: list[str]
    significant_deficiencies: list[str]
    credential_hash: str
    # hard booleans from ConfigInspectorAgent — these are authoritative
    all_controls_effective: bool = False
    per_control_effective: dict = field(default_factory=dict)


class ControlEvaluatorAgent:
    """
    LLM qualitative layer — mirrors app/agents/auditor.py.
    Receives hard findings from ConfigInspectorAgent as established facts.
    Hard booleans from the inspector always override LLM output in the final credential.
    """

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=30.0,
            max_retries=1,
        )

    async def evaluate(
        self,
        org_name: str,
        configs: list[dict],
        hard_findings: dict[str, ControlCheckResult],
    ) -> ControlEvaluation | None:
        """
        Call Claude with hard findings pre-established; parse qualitative response.
        Returns None on failure (non-fatal — caller proceeds with hard findings only).
        """
        try:
            hard_findings_block = "\n".join(
                f"  {ctrl}: {'PASS' if result.passed else 'FAIL'} — {result.finding}"
                for ctrl, result in hard_findings.items()
            )

            evidence_block = "\n".join(
                f"  {ctrl}: " + "; ".join(result.evidence[:3])
                for ctrl, result in hard_findings.items()
                if result.evidence
            )

            response = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": _USER_TEMPLATE.format(
                        org_name=org_name,
                        hard_findings_block=hard_findings_block,
                        evidence_block=evidence_block or "  (no additional evidence snippets)",
                    ),
                }],
            )

            raw = response.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(
                    l for l in lines
                    if not l.strip().startswith("```")
                ).strip()
            # Extract first { ... last } to tolerate trailing text
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError(f"No JSON object in LLM response: {raw[:200]}")
            try:
                data = json.loads(raw[start:end])
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON parse failed after extraction: {e}") from e

            # Enforce hard findings — LLM effective field is overridden by inspector
            assessments = data.get("control_assessments", [])
            for assessment in assessments:
                ctrl = assessment.get("control_id", "")
                if ctrl in hard_findings:
                    # Hard finding is authoritative
                    assessment["hard_finding"] = hard_findings[ctrl].passed
                    assessment["effective"] = hard_findings[ctrl].passed

            # Derive authoritative per-control and overall effectiveness
            per_control_effective = {
                ctrl: result.passed for ctrl, result in hard_findings.items()
            }
            all_effective = all(per_control_effective.values())

            # Material weaknesses = failed controls (hard finding = False)
            material_weaknesses = data.get("material_weaknesses", [])
            significant_deficiencies = data.get("significant_deficiencies", [])

            # Ensure failed controls are in material_weaknesses or significant_deficiencies
            failed_controls = [
                ctrl for ctrl, result in hard_findings.items() if not result.passed
            ]
            for ctrl in failed_controls:
                if ctrl not in material_weaknesses and ctrl not in significant_deficiencies:
                    material_weaknesses.append(ctrl)

            fields = {
                "control_assessments": assessments,
                "overall_assessment": str(data.get("overall_assessment", "")),
                "material_weaknesses": material_weaknesses,
                "significant_deficiencies": significant_deficiencies,
                "all_controls_effective": all_effective,
                "per_control_effective": per_control_effective,
            }
            credential_hash = hashlib.sha256(
                json.dumps(fields, sort_keys=True).encode()
            ).hexdigest()

            return ControlEvaluation(**fields, credential_hash=credential_hash)

        except Exception as exc:
            logger.warning(
                f"ControlEvaluatorAgent: evaluation failed (non-fatal) — "
                f"{type(exc).__name__}: {exc}"
            )
            return None
