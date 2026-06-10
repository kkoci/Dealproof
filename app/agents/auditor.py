"""
AuditorAgent — read-only TEE witness.

Receives the full negotiation transcript after settlement.
Produces a structured compliance report signed into the TDX quote.
Does not participate in negotiation rounds.

Scope: qualitative assessment only — genuine_negotiation and summary.
Structural checks (convergence, bounds, capitulation) belong exclusively
in app/picreds/constraints.py where they run deterministically from the
transcript without LLM judgment, which can misfire on edge cases.
"""
import json
import hashlib
import logging
import anthropic
from dataclasses import dataclass
from app.config import settings

logger = logging.getLogger(__name__)

_AUDIT_PROMPT = """You are a neutral compliance auditor inside a Trusted Execution Environment (TEE). Your output will be included in a cryptographic attestation.

You have witnessed a negotiation between a buyer and seller.

Buyer budget (hard ceiling): {buyer_budget}
Seller floor price (hard floor): {floor_price}
Final agreed price: {final_price}

Transcript:
---
{transcript}
---

Assess whether the negotiation reflects genuine autonomous bargaining — did both parties engage in authentic back-and-forth, or was it immediate/scripted capitulation? Look for evidence of independent strategic reasoning, meaningful concessions, and genuine adversarial positioning.

Do NOT assess price convergence or bounds — those are verified separately by deterministic constraint checks.

Respond with valid JSON only, no extra text:
{{"genuine_negotiation": true|false, "summary": "<one sentence describing the negotiation character>"}}"""


@dataclass
class AuditReport:
    genuine_negotiation: bool
    round_count: int
    final_price: float
    summary: str
    credential_hash: str


class AuditorAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def audit(
        self,
        transcript: list[dict],
        buyer_budget: float,
        floor_price: float,
        final_price: float,
    ) -> AuditReport | None:
        try:
            round_count = len({r.get("round", i) for i, r in enumerate(transcript)})

            response = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": _AUDIT_PROMPT.format(
                        buyer_budget=buyer_budget,
                        floor_price=floor_price,
                        final_price=final_price,
                        transcript=json.dumps(transcript, indent=2),
                    ),
                }],
            )

            raw = response.content[0].text.strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                start = raw.find("{")
                data, _ = json.JSONDecoder().raw_decode(raw, start)

            fields = {
                "genuine_negotiation": bool(data.get("genuine_negotiation", True)),
                "round_count": round_count,
                "final_price": final_price,
                "summary": str(data.get("summary", "")),
            }
            credential_hash = hashlib.sha256(
                json.dumps(fields, sort_keys=True).encode()
            ).hexdigest()

            return AuditReport(**fields, credential_hash=credential_hash)

        except Exception as exc:
            logger.warning(f"AuditorAgent: audit failed (non-fatal) — {type(exc).__name__}: {exc}")
            raise
