"""
πCreds conduct credential — Agent Rail Phase 3.

Reuses app.picreds.constraints.run_all_checks() and app.picreds.credential's
make_credential()/hash_credentials() UNMODIFIED — same "reuse core, don't fork"
pattern Phase 1 used for app.tee.attestation.sign_result and Phase 2 used for
the negotiation loop shape.

Two things stop this from being a thin call-through, though:

1. Role names. Core transcripts use "buyer"/"seller"; Agent Rail uses
   "buyer"/"supplier". _to_core_roles() adapts the transcript before handing
   it to constraints.py rather than touching that shared, tested module.

2. Sealed values. DealProof core's buyer_budget/floor_price are plain
   DealCreate fields, already visible in DealResult — so core's constraint
   findings freely embed the literal number, e.g. "within budget ($45)"
   (see app/picreds/constraints.py check_buyer_budget_respected). Agent
   Rail's whole product statement is that the buyer's ceiling and the
   supplier's floor are sealed from the platform operator — reusing core's
   finding strings verbatim would leak them straight into this credential's
   API response, which is public once a deal is agreed. audit_procurement_conduct()
   below keeps the (reused, authoritative) pass/fail booleans from
   constraints.py but writes its own finding text that never contains a number.

This module has no LLM call, unlike core's audit_deal_conduct(). Core's
qualitative layer (audit_deal_conduct/AuditorAgent) prompts Claude with the
literal buyer_budget/floor_price and trusts the model not to restate them in
free-text output — an acceptable risk for core's non-sealed values, but not
one this module takes on for values Agent Rail promises to keep sealed.
Phase 3 keeps the conduct credential fully deterministic; a redacted
qualitative layer is future work if it's wanted later.

Must be called from inside the negotiation background task (see
app/agentrail/routes.py) while buyer_ceiling/floor_price are still in scope —
they are never persisted to app.agentrail.store, so this can't be computed
later from a GET handler alone.
"""
from app.picreds.constraints import run_all_checks
from app.picreds.credential import hash_credentials, make_credential

_REDACTED_FINDINGS = {
    "buyer_budget": {
        True: "Every buyer proposal stayed within the sealed budget ceiling.",
        False: "One or more buyer proposals exceeded the sealed budget ceiling.",
    },
    "seller_floor": {
        True: "Every supplier proposal stayed at or above the sealed floor price.",
        False: "One or more supplier proposals fell below the sealed floor price.",
    },
    "capitulation": {
        True: "No sudden (>40%) single-round price jump by either side.",
        False: "At least one sudden (>40%) single-round price jump was detected.",
    },
    "convergence": {
        True: "Buyer and supplier prices moved monotonically toward each other.",
        False: "Buyer and/or supplier prices did not move monotonically toward each other.",
    },
}


def _to_core_roles(transcript: list[dict]) -> list[dict]:
    return [{**r, "role": "seller" if r.get("role") == "supplier" else r.get("role")} for r in transcript]


def audit_procurement_conduct(
    transcript: list[dict],
    buyer_ceiling: float,
    floor_price: float,
    final_price: float,
) -> dict:
    """Deterministic-only conduct audit. Returns a dict safe to expose over the
    API — no sealed value appears in any field, only pass/fail + redacted text."""
    core_transcript = _to_core_roles(transcript)
    constraint_results = run_all_checks(core_transcript, buyer_ceiling, floor_price)

    checks = {
        check_name: {
            "passed": result.passed,
            "finding": _REDACTED_FINDINGS[check_name][result.passed],
        }
        for check_name, result in constraint_results.items()
    }

    return {
        "checks": checks,
        "genuine_negotiation": all(r.passed for r in constraint_results.values()),
        "final_price": final_price,
    }


def build_credential(deal_id: str, audit_result: dict) -> tuple[dict, str]:
    """Wraps audit_result in a DealProofCredential envelope (matching core's
    make_credential shape) and returns (credential, picreds_hash)."""
    credential = make_credential("conduct", "deal", audit_result, deal_id, "")
    picreds_hash = hash_credentials([credential])
    return credential, picreds_hash
