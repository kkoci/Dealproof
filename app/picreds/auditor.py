"""
πCreds auditor — runs inside the TEE alongside the negotiation agents.

Two audit types:

  audit_agent_policy(agent_id, system_prompt)
    Reads an agent's system prompt and certifies the rules it is bound by.
    Produces a policy credential: "this agent cannot do X, must do Y."
    The system prompt is never returned — only the certified claims.

  audit_deal_conduct(transcript, buyer_budget, floor_price, final_price)
    Reviews the full negotiation transcript and verifies both agents
    complied with their hard constraints throughout.
    Produces a conduct credential: "neither agent violated their bounds."

Both calls use the same Anthropic API already in use for the agents.
The TEE attestation covers the auditor's output alongside the deal terms,
so a verifier can confirm the audit ran on the same execution.
"""
import json
import anthropic
from app.config import settings

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

Review the negotiation transcript below and verify both agents complied with their stated hard constraints.

Buyer budget (hard ceiling — buyer must never offer above this): {buyer_budget}
Seller floor price (hard floor — seller must never accept below this): {floor_price}
Final agreed price: {final_price}

Transcript:
---
{transcript}
---

Answer each question precisely:
1. Did the buyer offer above {buyer_budget} at any point?
2. Did the seller accept or counter-offer below {floor_price} at any point?
3. Is there any evidence of collusion (both agents coordinating against a third party)?
4. Did both parties engage in genuine back-and-forth negotiation?

Respond with valid JSON only, no extra text:
{{"buyer_budget_respected": true|false, "seller_floor_respected": true|false, "no_collusion_detected": true|false, "genuine_negotiation": true|false, "findings": ["<finding 1>"], "assessment": "<one sentence summary of negotiation conduct>"}}"""


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
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": _CONDUCT_PROMPT.format(
            buyer_budget=buyer_budget,
            floor_price=floor_price,
            final_price=final_price,
            transcript=json.dumps(transcript, indent=2),
        )}],
    )
    return _parse(response.content[0].text.strip())
