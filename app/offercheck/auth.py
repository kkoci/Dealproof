"""
Company auth — Phase 3 (see build_spec_offer_check.md).

A company registers once and gets an API key back (shown exactly once — only
its SHA-256 hash is stored). The key identifies the *employer* side across
sessions for bulk verification, the TA dashboard, and ATS webhook ingestion.

Deliberately unchanged: per-session `employer_token` links (Phase 1) still
work standalone and remain the only way to actually act on a session's
negotiation (submit a band, accept/counter/walk). Company auth adds a layer
on top — bulk session creation and read visibility — it does not replace the
per-session action tokens. See CLAUDE.md "Offer Check Architecture" for why.

Same limitation as Phase 1/2: in-memory only, no database. A server restart
invalidates every company's API key. Fine for a demo; not fine for companies
who need their key to survive a redeploy — that requires the Phase 3 database
migration this repo has deliberately deferred (see project memory).
"""
import hashlib
import secrets
from dataclasses import dataclass, field


@dataclass
class Company:
    id: str
    name: str
    api_key_hash: str
    webhook_secret: str
    plan: str = "individual"
    session_ids: list[str] = field(default_factory=list)
    ats_provider: str | None = None   # "greenhouse" | "lever" | "workday"
    ats_api_key: str | None = None    # never returned in any API response — write-only
    # Payment gating (see app.offercheck.credits) — additive, Phase 4.
    is_test_mode: bool = False   # set once, at registration, from the "oc_test_" key prefix
    is_unlimited: bool = False   # operator-only, see credits.grant_unlimited
    credit_balance: int = 0      # verification credits available — see credits.debit_for_verification


_COMPANIES: dict[str, Company] = {}
_API_KEY_INDEX: dict[str, str] = {}  # sha256(api_key) -> company_id


def reset() -> None:
    """Test-only: clear all companies between test cases."""
    _COMPANIES.clear()
    _API_KEY_INDEX.clear()


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def register_company(name: str, test_mode: bool = False) -> tuple[Company, str]:
    """
    Returns (company, raw_api_key). The raw key is never stored — only its hash.

    test_mode mints an "oc_test_"-prefixed key (vs. "oc_live_") and grants a starter
    credit balance immediately — see app.offercheck.credits' module docstring for why
    this is kept completely separate from the real-payment path. Both prefixes still
    satisfy the frontend's existing "oc_" well-formedness heuristic
    (offercheckCheckCompanyKey in api.js), so nothing there needs to change.
    """
    from app.offercheck import credits  # local import — avoids a module-load cycle (credits imports auth)

    prefix = "oc_test_" if test_mode else "oc_live_"
    raw_key = prefix + secrets.token_urlsafe(32)
    company = Company(
        id=secrets.token_urlsafe(12),
        name=name,
        api_key_hash=_hash_key(raw_key),
        webhook_secret=secrets.token_urlsafe(24),
        is_test_mode=test_mode,
    )
    if test_mode:
        credits.grant_credits(company, credits.TEST_STARTER_CREDITS)
    _COMPANIES[company.id] = company
    _API_KEY_INDEX[company.api_key_hash] = company.id
    return company, raw_key


def get_company_by_api_key(raw_key: str) -> Company | None:
    company_id = _API_KEY_INDEX.get(_hash_key(raw_key))
    return _COMPANIES.get(company_id) if company_id else None


def get_company(company_id: str) -> Company | None:
    return _COMPANIES.get(company_id)


def record_session(company: Company, session_id: str) -> None:
    company.session_ids.append(session_id)


def connect_ats(company: Company, provider: str, api_key: str) -> None:
    company.ats_provider = provider
    company.ats_api_key = api_key
