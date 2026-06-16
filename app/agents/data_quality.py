"""
DataQualityAgent — TEE-resident dataset quality assessor.

Runs before negotiation when quality_metrics are supplied in DealCreate.
Produces a DataQualityReport whose hash is included in the final TDX quote,
so a verifier can prove the agents negotiated with full knowledge of the
dataset's quality characteristics.

Report fields:
  completeness_score  float 0-1  — fraction of non-null values across all columns
  schema_consistent   bool       — no unexpected type coercions or shape mismatches
  label_distribution  dict       — class proportions if a label column is present
  quality_issues      list[str]  — specific problems (high null rate, imbalance, etc.)
  overall_quality     str        — "high" | "medium" | "low"
  summary             str        — one sentence assessment
  quality_hash        str        — SHA-256(report fields) — included in TDX report_data
"""
import hashlib
import json
import logging
from dataclasses import dataclass

import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

_QUALITY_SYSTEM_PROMPT = """You are a dataset quality assessor inside a Trusted Execution Environment.
You receive structured quality metrics about a dataset and produce a concise quality report.
Your report will be cryptographically attested and injected into an AI negotiation as a
TEE-verified quality credential. Be precise and factual — do not speculate beyond the metrics given.

Always respond with valid JSON only, no extra text:
{
  "completeness_score": <float 0.0-1.0>,
  "schema_consistent": <bool>,
  "label_distribution": <dict or null>,
  "quality_issues": [<string>, ...],
  "overall_quality": "<high|medium|low>",
  "summary": "<one sentence>"
}

Scoring guide:
- completeness_score: average of (1 - null_rate) across all columns
- overall_quality: high if completeness >= 0.95 and no critical issues,
                   medium if completeness >= 0.80 or minor issues,
                   low if completeness < 0.80 or critical issues present
- quality_issues: list specific problems, e.g. "12.4% null rate in pressure_hpa column",
                  "label imbalance: 84% normal vs 16% anomaly"
"""


@dataclass
class DataQualityReport:
    completeness_score: float
    schema_consistent: bool
    label_distribution: dict | None
    quality_issues: list[str]
    overall_quality: str
    summary: str
    quality_hash: str


class DataQualityAgent:
    def __init__(self) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def assess(self, data_description: str, quality_metrics: dict) -> DataQualityReport | None:
        """
        Assess dataset quality from pre-computed metrics.
        Returns None on any failure — quality assessment is non-fatal.
        """
        prompt = (
            f"Dataset description: {data_description}\n\n"
            f"Quality metrics:\n{json.dumps(quality_metrics, indent=2)}\n\n"
            "Produce a quality report for this dataset."
        )
        try:
            response = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=_QUALITY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                start = raw.find("{")
                data, _ = json.JSONDecoder().raw_decode(raw, start)

            report = DataQualityReport(
                completeness_score=float(data.get("completeness_score", 0.0)),
                schema_consistent=bool(data.get("schema_consistent", True)),
                label_distribution=data.get("label_distribution"),
                quality_issues=data.get("quality_issues") or [],
                overall_quality=data.get("overall_quality", "medium"),
                summary=data.get("summary", ""),
                quality_hash="",
            )
            report.quality_hash = _hash_report(report)
            return report
        except Exception as exc:
            logger.warning(f"DataQualityAgent.assess failed (non-fatal) — {exc}")
            return None


def _hash_report(report: DataQualityReport) -> str:
    payload = {
        "completeness_score": report.completeness_score,
        "schema_consistent": report.schema_consistent,
        "label_distribution": report.label_distribution,
        "quality_issues": sorted(report.quality_issues),
        "overall_quality": report.overall_quality,
        "summary": report.summary,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def build_quality_context(report: DataQualityReport, for_role: str) -> str:
    """
    Build the quality context string to inject into buyer/seller system prompts.
    for_role: "buyer" | "seller"
    """
    issues_text = "; ".join(report.quality_issues) if report.quality_issues else "none identified"
    label_text = ""
    if report.label_distribution:
        parts = [f"{k}: {v:.1%}" for k, v in report.label_distribution.items()]
        label_text = f" Label distribution: {', '.join(parts)}."

    if for_role == "buyer":
        return (
            f"Overall quality: {report.overall_quality.upper()} "
            f"(completeness {report.completeness_score:.1%}). "
            f"Issues: {issues_text}.{label_text} "
            f"Summary: {report.summary} "
            f"Use quality issues to justify a lower price if warranted."
        )
    else:
        return (
            f"Overall quality: {report.overall_quality.upper()} "
            f"(completeness {report.completeness_score:.1%}). "
            f"Issues: {issues_text}.{label_text} "
            f"Summary: {report.summary} "
            f"Be prepared to justify or discount based on known quality characteristics."
        )
