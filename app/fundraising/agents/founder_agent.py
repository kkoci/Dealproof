"""
FounderAgent — fundraising negotiation counterpart to SellerAgent.

Mirrors app/agents/seller.py exactly in structure (same method signatures,
same JSON response schema, same memory block pattern) so that run_negotiation()
from app/agents/negotiation.py can use FounderAgent in place of SellerAgent
without any modification to the loop.

The founder argues for pre-money valuation based on their company's hard metric
findings (MetricsInspectorAgent output), which are injected into the system
prompt as TEE-verified grounding. πCreds Phase 2 will check post-hoc that
claims made during negotiation were consistent with those hard findings.
"""
import json
import anthropic
from app.config import settings

_MEMORY_BLOCK = """

[MEMORY CONTEXT — recalled from prior fundraising rounds inside this TEE]
{memory_context}

Act on this. If this investor previously negotiated with you at a lower valuation,
adjust your opening ask and concession pace accordingly. A returning investor who
moved toward your floor quickly in a prior round may accept a higher opening ask.
"""

_METRICS_BLOCK = """

[TEE-VERIFIED COMPANY METRICS — authoritative hard findings]
These figures were computed deterministically inside the TEE from your submitted
financial data. They are cryptographically attested and cannot be disputed during
this negotiation. Your arguments for valuation MUST be consistent with them.

{metrics_context}

Do not claim growth rates, margins, or runway figures that these metrics do not
support. The investor has access to the ratios-only credential derived from these
same findings. Inconsistency between your claims and the hard findings is flagged
by an independent πCreds audit after the negotiation closes.
"""

FOUNDER_SYSTEM_PROMPT = """You are a startup founder agent negotiating pre-money valuation with a venture capital investor inside a Trusted Execution Environment (TEE).

Your goal: secure the highest possible pre-money valuation that is genuinely defensible from your company's metrics.

Target pre-money valuation (your opening ask): {valuation_ask}
Minimum acceptable pre-money valuation (floor — never go below this): {floor_valuation}
Company: {company_description}

Use your judgment to negotiate. Lead with metric-grounded arguments for your valuation.
If the investor raises concerns about your metrics, address them honestly — fabricating
stronger numbers than the hard findings support will be caught by the audit layer.

Hard constraints:
- Never accept below your floor valuation.
- Walk away if the investor won't come above your floor after several rounds.

Terms alongside valuation:
- Ownership percentage and investment amount are secondary to pre-money valuation.
- Be flexible on board composition and pro-rata rights if the valuation is right.

Always respond with valid JSON only, no extra text:
{{"action": "offer|counter|accept|reject", "price": <float>, "terms": {{"ownership_pct": <float>, "investment_amount": <float>, "notes": "<string>"}}, "reasoning": "<string>"}}
"""


def format_metrics_context(inspection_report: dict) -> str:
    """
    Format a serialised MetricsInspectionReport dict as a readable block
    for injection into the FounderAgent system prompt.

    The inspection_report is the dict produced by dataclasses.asdict(report)
    from MetricsInspectorAgent.inspect().
    """
    lines = []
    mom = inspection_report.get("mom_growth_computed")
    if mom is not None:
        verified = inspection_report.get("mom_growth_verified", False)
        lines.append(f"  MoM Revenue Growth: {mom * 100:.1f}%  ({'verified vs claim' if verified else 'diverges from claimed'})")

    margin = inspection_report.get("gross_margin_computed")
    if margin is not None:
        verified = inspection_report.get("gross_margin_verified", False)
        lines.append(f"  Gross Margin: {margin * 100:.1f}%  ({'verified vs claim' if verified else 'diverges from claimed'})")

    top_cust = inspection_report.get("top_customer_pct")
    if top_cust is not None:
        flag = inspection_report.get("customer_concentration_flag", False)
        lines.append(f"  Top Customer Concentration: {top_cust * 100:.1f}%  ({'FLAGGED — single customer ≥30%' if flag else 'within normal range'})")

    runway = inspection_report.get("runway_months_computed")
    if runway is not None:
        flag = inspection_report.get("runway_flag", False)
        lines.append(f"  Runway: {runway:.1f} months  ({'FLAGGED — below 6 months' if flag else 'healthy'})")

    churn = inspection_report.get("churn_rate_computed")
    if churn is not None:
        flag = inspection_report.get("churn_flag", False)
        lines.append(f"  Monthly Churn: {churn * 100:.2f}%  ({'FLAGGED — above 5%' if flag else 'within range'})")

    arr_delta = inspection_report.get("arr_delta_pct")
    if arr_delta is not None:
        verified = inspection_report.get("arr_consistency_verified", False)
        lines.append(f"  ARR Consistency: {arr_delta * 100:+.1f}% delta  ({'verified' if verified else 'FLAGGED — reported ARR diverges from computed'})")

    if not lines:
        return "(no metric findings available)"
    return "\n".join(lines)


class FounderAgent:
    """
    Negotiates pre-money valuation on behalf of a startup founder.

    Drop-in replacement for SellerAgent in run_negotiation():
      - .floor_price  → minimum acceptable valuation (used by ArbitratorAgent)
      - .make_offer(history) → same signature as SellerAgent.make_offer()
    """

    def __init__(
        self,
        floor_valuation: float,
        valuation_ask: float,
        company_description: str,
        inspection_report: dict | None = None,
        memory_context: str = "",
    ):
        """
        Parameters
        ----------
        floor_valuation : float
            Minimum acceptable pre-money valuation. Exposed as .floor_price
            for compatibility with run_negotiation() / ArbitratorAgent.
        valuation_ask : float
            Opening ask / target pre-money valuation.
        company_description : str
            Brief description of the company and round context.
        inspection_report : dict | None
            Serialised MetricsInspectionReport (dataclasses.asdict output).
            When provided, injected as TEE-verified grounding.
        memory_context : str
            Recalled memories from prior negotiations via Contexto sidecar.
        """
        self.floor_price = floor_valuation          # negotiation.py / arbitrator compatibility
        self.valuation_ask = valuation_ask
        self.company_description = company_description
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        self.system_prompt = FOUNDER_SYSTEM_PROMPT.format(
            floor_valuation=floor_valuation,
            valuation_ask=valuation_ask,
            company_description=company_description,
        )
        if inspection_report:
            metrics_str = format_metrics_context(inspection_report)
            self.system_prompt += _METRICS_BLOCK.format(metrics_context=metrics_str)
        if memory_context:
            self.system_prompt += _MEMORY_BLOCK.format(memory_context=memory_context)

    async def make_offer(self, history: list[dict]) -> dict:
        """Mirror SellerAgent.make_offer() — same signature, used by run_negotiation()."""
        messages = self._build_messages(history)

        response = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=self.system_prompt,
            messages=messages,
        )

        raw = response.content[0].text.strip()
        return self._parse_response(raw)

    def _build_messages(self, history: list[dict]) -> list[dict]:
        if not history:
            return [{"role": "user", "content": "Start the negotiation. Make your opening valuation offer."}]

        messages = []
        for entry in history:
            # investor = "buyer" in run_negotiation vocabulary → user turn for founder
            role = "user" if entry["role"] == "buyer" else "assistant"
            messages.append({"role": role, "content": json.dumps(entry["content"])})

        if messages and messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": "Continue the negotiation based on the investor's last response."})

        return messages

    def _parse_response(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            data, _ = json.JSONDecoder().raw_decode(raw, start)

        return {
            "action": data.get("action", "offer"),
            "price": float(data.get("price") or 0),
            "terms": data.get("terms", {}),
            "reasoning": data.get("reasoning", ""),
        }
