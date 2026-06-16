"""
DataCredentialAgent — TEE-attested team dynamics credential.

Reads a TinyCloud conversation corpus inside the TEE and produces a structured
investor-legible credential assessing team decision velocity, collaboration,
commitment follow-through, and execution signal.

Called by POST /api/deals/{id}/credential after a deal is agreed.
Output becomes TeamCredential.subject — attested in the TDX quote as-is,
including {"error": "assessment_failed"} on parse failure.
"""
import json
import logging
import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a credential auditor for investor due-diligence on a startup team.
You receive a corpus of meeting/call transcripts and conversation summaries.
Return ONLY a JSON object, no prose, no markdown.

Assess these properties:
- decision_velocity: int, avg rounds/meetings to reach a concrete decision (lower=faster)
- collaboration_balance: float 0.0-1.0, how evenly distributed is speaking time (1.0=equal)
- commitment_count: int, concrete next-step commitments made across all conversations
- conflict_resolution: "constructive" | "avoidant" | "unresolved" | "insufficient_data"
- technical_depth: "deep" | "moderate" | "surface" | "insufficient_data"
- execution_signal: "strong" | "moderate" | "weak" | "insufficient_data"
  (based on: do they follow up on prior commitments across meetings?)
- summary: str, one sentence max 30 words, investor-legible

{"decision_velocity": <int>, "collaboration_balance": <float>, "commitment_count": <int>, "conflict_resolution": "<string>", "technical_depth": "<string>", "execution_signal": "<string>", "summary": "<string>"}"""


def _build_corpus_text(conversations: list[dict]) -> str:
    """Build prompt text from conversations, preferring summary over raw sentences."""
    lines = []
    for i, conv in enumerate(conversations, 1):
        header = f"[{i}] {conv.get('title', f'Conversation {i}')} ({conv.get('source', '')}, {conv.get('started_at', '')[:10]})"
        summary = conv.get("summary")
        if summary:
            lines.append(f"{header}\nSummary: {summary}")
        else:
            sentences = conv.get("sentences") or []
            if sentences:
                text = " ".join(s["text"] for s in sentences[:50])
                lines.append(f"{header}\nTranscript excerpt: {text}")
    return "\n\n".join(lines)


class DataCredentialAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def assess(self, conversations: list[dict]) -> dict:
        corpus_text = _build_corpus_text(conversations)
        if not corpus_text.strip():
            return {"error": "assessment_failed"}

        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": corpus_text}],
        )

        raw = response.content[0].text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            if start == -1:
                return {"error": "assessment_failed"}
            try:
                data, _ = json.JSONDecoder().raw_decode(raw, start)
                return data
            except Exception:
                return {"error": "assessment_failed"}
