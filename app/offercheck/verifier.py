"""
Offer verification logic — Phase 1: software only, no TEE, no LLM.

Checks that a candidate's reported competing offer is internally consistent
("not obviously fabricated"). This is a plausibility screen, not a legal
verification — Phase 2 adds real PDF offer-letter parsing inside a TDX
enclave. Never returns or logs the candidate's raw numbers to the employer;
callers must only surface `ConsistencyCheck.verified` / `.issues`.
"""
from datetime import date, datetime, timedelta

from app.offercheck.schemas import CompetingOffer, ConsistencyCheck

MAX_PLAUSIBLE_BASE = 5_000_000.0
MAX_BONUS_TO_BASE_RATIO = 3.0
MAX_EQUITY_TO_BASE_RATIO = 10.0
MAX_START_DATE_LEAD_DAYS = 365
MAX_START_DATE_PAST_DAYS = 30
MAX_ASK_TO_TOTAL_COMP_RATIO = 1.5  # candidate ask vs. their own reported total comp


def _parse_start_date(raw: str) -> date | None:
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def check_consistency(offer: CompetingOffer, candidate_ask: float) -> ConsistencyCheck:
    issues: list[str] = []

    if not offer.company.strip():
        issues.append("company name is blank")
    if not offer.role.strip():
        issues.append("role title is blank")

    if offer.base_salary > MAX_PLAUSIBLE_BASE:
        issues.append("base salary exceeds plausible range")

    if offer.base_salary > 0 and offer.bonus > offer.base_salary * MAX_BONUS_TO_BASE_RATIO:
        issues.append("bonus is implausibly large relative to base salary")

    if offer.base_salary > 0 and offer.equity_value > offer.base_salary * MAX_EQUITY_TO_BASE_RATIO:
        issues.append("equity value is implausibly large relative to base salary")

    start = _parse_start_date(offer.start_date)
    if start is None:
        issues.append("start date is not a valid ISO-8601 date")
    else:
        today = date.today()
        if start < today - timedelta(days=MAX_START_DATE_PAST_DAYS):
            issues.append("start date is more than 30 days in the past")
        if start > today + timedelta(days=MAX_START_DATE_LEAD_DAYS):
            issues.append("start date is more than a year out")

    total_comp = offer.base_salary + offer.bonus + offer.equity_value
    if total_comp > 0 and candidate_ask > total_comp * MAX_ASK_TO_TOTAL_COMP_RATIO:
        issues.append("candidate ask is far above the reported competing total comp")

    if candidate_ask <= 0:
        issues.append("candidate ask must be positive")

    return ConsistencyCheck(verified=len(issues) == 0, issues=issues)
