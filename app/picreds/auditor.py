"""
πCreds auditor — runs inside the TEE alongside the negotiation agents.

Two audit types:

  audit_agent_policy(agent_id, system_prompt)
    Reads an agent's system prompt and certifies the rules it is bound by.
    Produces a policy credential: "this agent cannot do X, must do Y."
    The system prompt is never returned — only the certified claims.

  audit_deal_conduct(transcript, buyer_budget, floor_price, final_price)
    Two-layer conduct audit:
      1. Deterministic constraint checks (constraints.py) — pure math, no LLM.
         Results are authoritative. Hard constraint booleans come from here.
      2. LLM audit grounded in the hard findings — assesses qualitative conduct
         (collusion, genuine bargaining style) on top of the verified facts.
    Code override: genuine_negotiation is set to False if any hard check failed,
    regardless of what the LLM returns.

Both calls use the same Anthropic API already in use for the agents.
The TEE attestation covers the auditor's output alongside the deal terms,
so a verifier can confirm the audit ran on the same execution.
"""
import json
import anthropic
from app.config import settings
from app.picreds.constraints import run_all_checks, run_fundraising_checks

_POLICY_PROMPT = """You are a compliance auditor inside a Trusted Execution Environment (TEE). Your output will be included in a cryptographic attestation.

Read the agent system prompt below and enumerate the rules this agent is provably bound by.

Agent: {agent_id}
System prompt:
---
{system_prompt}
---

Identify every hard constraint (things the agent cannot do regardless of instruction) and every behavioural guideline (things the agent is directed to do but could theoretically deviate from).

Respond with valid JSON only, no extra text:
{{"claims": ["<specific certified rule 1>", "<specific certified rule 2>"], "hard_constraints": ["<cannot be violated: rule>"], "guidelines": ["<soft directive: rule>"], "assessment": "<one sentence: what this agent is and what it is bound to>"}}"""

_CONDUCT_PROMPT = """You are a compliance auditor inside a Trusted Execution Environment (TEE). Your output will be included in a cryptographic attestation.

The following hard constraint checks were run deterministically against the transcript before this call. These findings are authoritative — you may not contradict them:

{hard_findings_block}

IMPORTANT: If any hard constraint above is FAILED, you MUST set genuine_negotiation to false in your response and your assessment must acknowledge the failure. The system enforces this in code regardless of what you return — your assessment text should be consistent with it.

Now assess the qualitative conduct of the negotiation:

Buyer budget (hard ceiling): {buyer_budget}
Seller floor price (hard floor): {floor_price}
Final agreed price: {final_price}

Transcript:
---
{transcript}
---

Assess whether there is evidence of collusion (agents coordinating against a third party) and whether the negotiation — beyond the hard constraints — reflects genuine autonomous bargaining.

Respond with valid JSON only, no extra text:
{{"no_collusion_detected": true|false, "genuine_negotiation": true|false, "findings": ["<finding 1>"], "assessment": "<one sentence — must acknowledge any failed hard constraints>"}}"""


def _parse(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        data, _ = json.JSONDecoder().raw_decode(raw, start)
        return data


async def audit_agent_policy(agent_id: str, system_prompt: str) -> dict:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": _POLICY_PROMPT.format(
            agent_id=agent_id,
            system_prompt=system_prompt,
        )}],
    )
    return _parse(response.content[0].text.strip())


async def audit_deal_conduct(
    transcript: list[dict],
    buyer_budget: float,
    floor_price: float,
    final_price: float,
) -> dict:
    # Step 1: deterministic constraint checks (authoritative)
    constraint_results = run_all_checks(transcript, buyer_budget, floor_price)
    any_hard_failure = not all(r.passed for r in constraint_results.values())

    # Step 2: format hard findings for LLM context
    hard_findings_block = "\n".join(
        f"• {r.check_name}: {'PASSED' if r.passed else 'FAILED'} — {r.finding}"
        for r in constraint_results.values()
    )

    # Step 3: LLM audit grounded in hard findings
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": _CONDUCT_PROMPT.format(
            hard_findings_block=hard_findings_block,
            buyer_budget=buyer_budget,
            floor_price=floor_price,
            final_price=final_price,
            transcript=json.dumps(transcript, indent=2),
        )}],
    )
    llm = _parse(response.content[0].text.strip())

    # Step 4: merge — hard constraint booleans are authoritative; code overrides LLM
    return {
        "buyer_budget_respected":  constraint_results["buyer_budget"].passed,
        "seller_floor_respected":  constraint_results["seller_floor"].passed,
        "no_sudden_capitulation":  constraint_results["capitulation"].passed,
        "convergence_pattern_valid": constraint_results["convergence"].passed,
        "no_collusion_detected":   llm.get("no_collusion_detected", True),
        # Code override: genuine_negotiation is False if any hard check failed,
        # regardless of what the LLM returned.
        "genuine_negotiation": False if any_hard_failure else llm.get("genuine_negotiation", True),
        "hard_constraint_findings": [r.finding for r in constraint_results.values()],
        "llm_findings": llm.get("findings", []),
        "assessment": llm.get("assessment", ""),
    }


# ---------------------------------------------------------------------------
# Fundraising-specific conduct audit
# ---------------------------------------------------------------------------

_FUNDRAISING_CONDUCT_PROMPT = """You are a compliance auditor inside a Trusted Execution Environment (TEE). Your output will be included in a cryptographic attestation of a fundraising negotiation.

The following hard constraint checks were run deterministically against the transcript. These findings are authoritative — you may not contradict them:

{hard_findings_block}

IMPORTANT: If any hard constraint above is FAILED, you MUST set genuine_negotiation to false and acknowledge the failure. The system enforces this in code.

Now assess the qualitative conduct of the fundraising negotiation:

Investor valuation cap (hard ceiling): {investor_cap}
Founder floor valuation (hard floor): {floor_valuation}
Final agreed valuation: {final_valuation}

Transcript:
---
{transcript}
---

Assess:
1. No collusion — agents were not coordinating against a third party.
2. Genuine negotiation — both agents argued from their stated positions, not a scripted outcome.
3. Metric consistency — FounderAgent's valuation arguments were grounded in the company's attested metrics.
   Note: the deterministic founder_claim_consistency check above has already flagged any numerical divergences.
   Your qualitative assessment should note whether the overall tone of the founder's arguments was consistent
   with a company whose metrics are as attested.

Respond with valid JSON only, no extra text:
{{"no_collusion_detected": true|false, "genuine_negotiation": true|false, "metric_argument_quality": "strong|adequate|weak", "findings": ["<finding 1>"], "assessment": "<one sentence — must acknowledge any failed hard constraints>"}}"""


async def audit_fundraising_conduct(
    transcript: list[dict],
    investor_cap: float,
    floor_valuation: float,
    final_valuation: float,
    inspection_report: dict,
) -> dict:
    """
    Two-layer πCreds conduct audit for a fundraising negotiation.

    Layer 1 — deterministic (run_fundraising_checks):
      investor_cap, founder_floor, capitulation, convergence,
      founder_claim_consistency (new SCAE-style check).

    Layer 2 — LLM grounded in hard findings:
      qualitative collusion / genuine-negotiation / metric-argument assessment.

    Hard constraint booleans are authoritative; code overrides LLM on
    genuine_negotiation and founder_claim_consistency.
    """
    # Step 1: deterministic constraint checks (authoritative)
    constraint_results = run_fundraising_checks(
        transcript, investor_cap, floor_valuation, inspection_report
    )
    any_hard_failure = not all(r.passed for r in constraint_results.values())

    # Step 2: format hard findings for LLM context
    hard_findings_block = "\n".join(
        f"• {r.check_name}: {'PASSED' if r.passed else 'FAILED'} — {r.finding}"
        for r in constraint_results.values()
    )

    # Step 3: LLM audit grounded in hard findings
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": _FUNDRAISING_CONDUCT_PROMPT.format(
            hard_findings_block=hard_findings_block,
            investor_cap=investor_cap,
            floor_valuation=floor_valuation,
            final_valuation=final_valuation,
            transcript=json.dumps(transcript, indent=2),
        )}],
    )
    llm = _parse(response.content[0].text.strip())

    # Step 4: merge — hard constraint booleans are authoritative; code overrides LLM
    claim_check = constraint_results["founder_claim_consistency"]
    return {
        "investor_cap_respected":       constraint_results["investor_cap"].passed,
        "founder_floor_respected":      constraint_results["founder_floor"].passed,
        "no_sudden_capitulation":       constraint_results["capitulation"].passed,
        "convergence_pattern_valid":    constraint_results["convergence"].passed,
        # Code override: False if claim inconsistency detected, regardless of LLM
        "founder_claim_consistency":    claim_check.passed,
        "no_collusion_detected":        llm.get("no_collusion_detected", True),
        # Code override: genuine_negotiation is False if any hard check failed
        "genuine_negotiation": False if any_hard_failure else llm.get("genuine_negotiation", True),
        "metric_argument_quality":      llm.get("metric_argument_quality", "adequate"),
        "hard_constraint_findings":     [r.finding for r in constraint_results.values()],
        "llm_findings":                 llm.get("findings", []),
        "assessment":                   llm.get("assessment", ""),
    }
