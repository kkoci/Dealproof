"""
Deterministic constraint checks for πCreds conduct audit.

Pure functions — no LLM calls. Verifiable by anyone from the transcript alone.
Results feed into audit_deal_conduct() as authoritative grounding before the
LLM runs. Hard constraint booleans in the final credential come from here,
not from the LLM.

check_minimum_rounds is intentionally absent. A fast deal (e.g. seller opens
at a price the buyer genuinely finds acceptable) is not a protocol violation.
Requiring multiple rounds would produce false positives on legitimate quick
agreements and is not a meaningful collusion signal.
"""
from dataclasses import dataclass, field

CAPITULATION_THRESHOLD = 0.40


@dataclass
class CheckResult:
    check_name: str
    passed: bool
    finding: str
    evidence: list[dict] = field(default_factory=list)


def check_buyer_budget_respected(transcript: list[dict], buyer_budget: float) -> CheckResult:
    violations = [
        r for r in transcript
        if r.get("role") == "buyer" and r.get("price", 0) > buyer_budget
    ]
    if violations:
        prices = [r["price"] for r in violations]
        return CheckResult(
            check_name="buyer_budget_respected",
            passed=False,
            finding=f"Buyer offered above budget (${buyer_budget}) at prices: {prices}",
            evidence=violations,
        )
    return CheckResult(
        check_name="buyer_budget_respected",
        passed=True,
        finding=f"All buyer offers were within budget (${buyer_budget})",
    )


def check_seller_floor_respected(transcript: list[dict], floor_price: float) -> CheckResult:
    violations = [
        r for r in transcript
        if r.get("role") == "seller" and r.get("price", float("inf")) < floor_price
    ]
    if violations:
        prices = [r["price"] for r in violations]
        return CheckResult(
            check_name="seller_floor_respected",
            passed=False,
            finding=f"Seller offered below floor price (${floor_price}) at prices: {prices}",
            evidence=violations,
        )
    return CheckResult(
        check_name="seller_floor_respected",
        passed=True,
        finding=f"All seller offers were at or above floor price (${floor_price})",
    )


def check_no_sudden_capitulation(
    transcript: list[dict],
    threshold: float = CAPITULATION_THRESHOLD,
) -> CheckResult:
    """
    No agent should move more than `threshold` fraction of their previous price
    in a single round. Flags scripted or colluding outcomes.
    Default threshold: 0.40 (40%). Configurable per call.
    """
    by_role: dict[str, list[dict]] = {"buyer": [], "seller": []}
    for r in transcript:
        role = r.get("role")
        if role in by_role:
            by_role[role].append(r)

    violations = []
    for role, rounds in by_role.items():
        for i in range(1, len(rounds)):
            prev_price = rounds[i - 1].get("price", 0)
            curr_price = rounds[i].get("price", 0)
            if prev_price == 0:
                continue
            jump = abs(curr_price - prev_price) / abs(prev_price)
            if jump > threshold:
                violations.append({
                    **rounds[i],
                    "_jump_pct": round(jump * 100, 1),
                    "_prev_price": prev_price,
                })

    if violations:
        desc = ", ".join(
            f"{v['role']} round {v['round']}: "
            f"${v['_prev_price']}→${v['price']} ({v['_jump_pct']}%)"
            for v in violations
        )
        return CheckResult(
            check_name="no_sudden_capitulation",
            passed=False,
            finding=f"Sudden price jump(s) exceeding {int(threshold * 100)}%: {desc}",
            evidence=violations,
        )
    return CheckResult(
        check_name="no_sudden_capitulation",
        passed=True,
        finding=f"No sudden price jumps exceeding {int(threshold * 100)}% detected",
    )


def check_convergence_pattern(transcript: list[dict]) -> CheckResult:
    """
    Buyer offers should be non-decreasing over time (moving up toward seller).
    Seller offers should be non-increasing over time (moving down toward buyer).
    Violations indicate non-convergent or chaotic negotiation dynamics.
    """
    buyer_rounds = [r for r in transcript if r.get("role") == "buyer"]
    seller_rounds = [r for r in transcript if r.get("role") == "seller"]

    violations = []

    for i in range(1, len(buyer_rounds)):
        if buyer_rounds[i].get("price", 0) < buyer_rounds[i - 1].get("price", 0):
            violations.append({
                **buyer_rounds[i],
                "_expected": "non-decreasing",
                "_prev_price": buyer_rounds[i - 1]["price"],
            })

    for i in range(1, len(seller_rounds)):
        if seller_rounds[i].get("price", 0) > seller_rounds[i - 1].get("price", 0):
            violations.append({
                **seller_rounds[i],
                "_expected": "non-increasing",
                "_prev_price": seller_rounds[i - 1]["price"],
            })

    if violations:
        desc = ", ".join(
            f"{v['role']} round {v['round']}: ${v['_prev_price']}→${v['price']}"
            for v in violations
        )
        return CheckResult(
            check_name="convergence_pattern",
            passed=False,
            finding=f"Non-convergent price movement: {desc}",
            evidence=violations,
        )
    return CheckResult(
        check_name="convergence_pattern",
        passed=True,
        finding="Prices converged monotonically throughout negotiation",
    )


def run_all_checks(
    transcript: list[dict],
    buyer_budget: float,
    floor_price: float,
    capitulation_threshold: float = CAPITULATION_THRESHOLD,
) -> dict[str, CheckResult]:
    return {
        "buyer_budget": check_buyer_budget_respected(transcript, buyer_budget),
        "seller_floor": check_seller_floor_respected(transcript, floor_price),
        "capitulation": check_no_sudden_capitulation(transcript, capitulation_threshold),
        "convergence": check_convergence_pattern(transcript),
    }
