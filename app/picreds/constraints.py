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

Fundraising-specific checks (run_fundraising_checks):
  check_founder_claim_consistency — scans FounderAgent reasoning text for stated
    metric claims (growth %, margin %, runway months) and flags material divergence
    from MetricsInspectorAgent's hard findings.  Same SCAE defence as ARR inflation
    detection: "is this agent being honest about the number" applied one level up
    from "is this number real."
  check_investor_cap_respected — FounderAgent (seller role) never accepts below
    floor; InvestorAgent (buyer role) never offers above their cap.  Reuses the
    existing buyer_budget / seller_floor checks under fundraising role labels.
"""
import re
from dataclasses import dataclass, field

CAPITULATION_THRESHOLD = 0.40

# Relative tolerance when matching natural-language metric claims against hard
# findings.  Wider than MetricsInspectorAgent's CLAIM_TOLERANCE (5%) because
# agents naturally round numbers in prose — we only want to catch material
# overstatements, not rounding noise.
CLAIM_CONSISTENCY_TOLERANCE = 0.15  # 15% relative


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


# ---------------------------------------------------------------------------
# Fundraising-specific checks
# ---------------------------------------------------------------------------

# Regex patterns for metric claims in FounderAgent reasoning prose.
# Two orderings are common: "25% MoM growth" (number-first) and
# "MoM growth is 25%" (keyword-first). Each metric has both patterns.

# Growth — number-first: "25% MoM growth" / "25% monthly growth"
_GROWTH_NUM_FIRST = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*"
    r"(?:mom|month[-_.]?over[-_.]?month|monthly\s+(?:revenue\s+)?growth|growth\s+rate)",
    re.IGNORECASE,
)
# Growth — keyword-first: "MoM growth is 25%" / "growth rate of 9%"
# mom(?:\s+growth(?:\s+rate)?)? handles "MoM", "MoM growth", "MoM growth rate"
_GROWTH_KWD_FIRST = re.compile(
    r"(?:mom(?:\s+growth(?:\s+rate)?)?|month[-_.]?over[-_.]?month|"
    r"monthly\s+(?:revenue\s+)?growth(?:\s+rate)?|growth\s+rate)"
    r"\s+(?:of|is|was|at|:)?\s*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

# Margin — number-first: "76% gross margin"
_MARGIN_NUM_FIRST = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*(?:gross\s+)?margin",
    re.IGNORECASE,
)
# Margin — keyword-first: "gross margin is 76%" / "margin of 76%"
# gross(?:\s+margin)? handles "gross", "gross margin"
_MARGIN_KWD_FIRST = re.compile(
    r"(?:gross\s+)?margin\s+(?:of|is|was|at|:)?\s*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

# Runway — number-first: "30 months of runway"
_RUNWAY_NUM_FIRST = re.compile(
    r"(\d+(?:\.\d+)?)\s*months?\s*(?:of\s+)?(?:runway|remaining\s+runway)",
    re.IGNORECASE,
)
# Runway — keyword-first: "runway of 30 months" / "runway is 30 months"
_RUNWAY_KWD_FIRST = re.compile(
    r"runway\s+(?:of|is|was|at|:)?\s*(\d+(?:\.\d+)?)\s*months?",
    re.IGNORECASE,
)

# Churn — number-first: "3% monthly churn"
_CHURN_NUM_FIRST = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*(?:monthly\s+)?churn(?:\s+rate)?",
    re.IGNORECASE,
)
# Churn — keyword-first: "churn rate is 3%" / "monthly churn of 3%"
# monthly(?:\s+churn)? handles "monthly", "monthly churn", "monthly churn rate"
_CHURN_KWD_FIRST = re.compile(
    r"(?:monthly\s+)?churn(?:\s+rate)?\s+(?:of|is|was|at|:)?\s*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)


def _extract_claims_from_reasoning(reasoning: str) -> dict[str, list[float]]:
    """
    Extract quantitative metric claims from a FounderAgent reasoning string.

    Handles both "25% MoM growth" (number-first) and "MoM growth is 25%"
    (keyword-first) orderings. Returns a dict mapping metric name → list of
    claimed values (decimal form). Deduplicates values within 0.1% to avoid
    double-counting the same figure matched by both patterns.
    """
    def _pct_vals(patterns: list) -> list[float]:
        vals = []
        for pat in patterns:
            for m in pat.finditer(reasoning):
                vals.append(float(m.group(1)) / 100.0)
        return _dedup(vals)

    def _raw_vals(patterns: list) -> list[float]:
        vals = []
        for pat in patterns:
            for m in pat.finditer(reasoning):
                vals.append(float(m.group(1)))
        return _dedup(vals)

    def _dedup(vals: list[float]) -> list[float]:
        out: list[float] = []
        for v in vals:
            if not any(abs(v - existing) < 0.001 for existing in out):
                out.append(v)
        return out

    claims: dict[str, list[float]] = {}

    growth = _pct_vals([_GROWTH_NUM_FIRST, _GROWTH_KWD_FIRST])
    if growth:
        claims["mom_growth"] = growth

    margin = _pct_vals([_MARGIN_NUM_FIRST, _MARGIN_KWD_FIRST])
    if margin:
        claims["gross_margin"] = margin

    runway = _raw_vals([_RUNWAY_NUM_FIRST, _RUNWAY_KWD_FIRST])
    if runway:
        claims["runway_months"] = runway

    churn = _pct_vals([_CHURN_NUM_FIRST, _CHURN_KWD_FIRST])
    if churn:
        claims["churn_rate"] = churn

    return claims


def check_founder_claim_consistency(
    transcript: list[dict],
    inspection_report: dict,
    claim_tolerance: float = CLAIM_CONSISTENCY_TOLERANCE,
) -> CheckResult:
    """
    Scan every FounderAgent (seller-role) reasoning block for stated metric
    values and flag any that materially diverge from MetricsInspectorAgent's
    hard findings.

    This is the fundraising analogue of the ARR inflation SCAE check:
      ARR check: "is the number in the submitted data real?"
      This check: "is the negotiating agent honest about the number?"

    Hard findings used (all optional — missing keys are skipped):
      mom_growth_computed   → compared against growth claims
      gross_margin_computed → compared against margin claims
      runway_months_computed → compared against runway claims
      churn_rate_computed   → compared against churn claims

    A claim diverges if:
      abs(claimed - hard) / abs(hard) > claim_tolerance
    """
    # Map metric name → (hard_value, human_label)
    hard = {
        "mom_growth": (inspection_report.get("mom_growth_computed"), "MoM growth"),
        "gross_margin": (inspection_report.get("gross_margin_computed"), "gross margin"),
        "runway_months": (inspection_report.get("runway_months_computed"), "runway"),
        "churn_rate": (inspection_report.get("churn_rate_computed"), "monthly churn"),
    }

    violations = []
    for entry in transcript:
        if entry.get("role") != "seller":
            continue
        reasoning = entry.get("reasoning", "")
        if not reasoning:
            continue

        claimed = _extract_claims_from_reasoning(reasoning)
        for metric, claimed_values in claimed.items():
            hard_value, label = hard.get(metric, (None, metric))
            if hard_value is None or abs(hard_value) == 0:
                continue
            for cv in claimed_values:
                relative_error = abs(cv - hard_value) / abs(hard_value)
                if relative_error > claim_tolerance:
                    violations.append({
                        "round": entry.get("round"),
                        "metric": label,
                        "claimed": cv,
                        "hard_finding": hard_value,
                        "relative_error_pct": round(relative_error * 100, 1),
                    })

    if violations:
        desc = "; ".join(
            f"round {v['round']}: claimed {v['metric']}={v['claimed']*100:.1f}% "
            f"vs hard finding {v['hard_finding']*100:.1f}% "
            f"({v['relative_error_pct']}% divergence)"
            if v["metric"] != "runway"
            else
            f"round {v['round']}: claimed runway={v['claimed']:.1f}mo "
            f"vs hard finding {v['hard_finding']:.1f}mo "
            f"({v['relative_error_pct']}% divergence)"
            for v in violations
        )
        return CheckResult(
            check_name="founder_claim_consistency",
            passed=False,
            finding=f"FounderAgent stated metric(s) materially diverge from hard findings: {desc}",
            evidence=violations,
        )

    return CheckResult(
        check_name="founder_claim_consistency",
        passed=True,
        finding=(
            "No material divergence detected between FounderAgent's stated metrics "
            "and MetricsInspectorAgent's hard findings"
        ),
    )


def check_investor_cap_respected(
    transcript: list[dict],
    investor_cap: float,
) -> CheckResult:
    """
    InvestorAgent (buyer role in run_negotiation) must never offer above their
    stated maximum valuation cap.  Thin wrapper around check_buyer_budget_respected
    with fundraising-appropriate labels.
    """
    result = check_buyer_budget_respected(transcript, investor_cap)
    return CheckResult(
        check_name="investor_cap_respected",
        passed=result.passed,
        finding=result.finding.replace("budget", "valuation cap"),
        evidence=result.evidence,
    )


def run_fundraising_checks(
    transcript: list[dict],
    investor_cap: float,
    floor_valuation: float,
    inspection_report: dict,
    capitulation_threshold: float = CAPITULATION_THRESHOLD,
    claim_tolerance: float = CLAIM_CONSISTENCY_TOLERANCE,
) -> dict[str, CheckResult]:
    """
    Full deterministic check suite for a fundraising negotiation.

    Combines the four existing Deal Room checks (cap/floor/capitulation/convergence)
    with the new fundraising-specific founder_claim_consistency check.

    The roles in run_negotiation() map as:
      seller → FounderAgent  (floor_valuation = floor_price)
      buyer  → InvestorAgent (investor_cap   = buyer_budget)
    """
    return {
        "investor_cap":          check_investor_cap_respected(transcript, investor_cap),
        "founder_floor":         check_seller_floor_respected(transcript, floor_valuation),
        "capitulation":          check_no_sudden_capitulation(transcript, capitulation_threshold),
        "convergence":           check_convergence_pattern(transcript),
        "founder_claim_consistency": check_founder_claim_consistency(
            transcript, inspection_report, claim_tolerance
        ),
    }
