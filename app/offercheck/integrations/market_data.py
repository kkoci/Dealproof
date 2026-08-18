"""
Market-data integration — external salary comparator for a closed Offer Check
session. Sibling to `negotiation.final_gap_pct` (see that function's
docstring): final_gap_pct is a *relative* external anchor (did the number
move from the employer's own opening position); this is an *absolute* one
(does the final number look sane against real third-party comparators the
negotiating agent never had access to or control over).

Data source: PayScale's Compensation Data API (role/title + location salary
percentiles), following this repo's existing external-integration convention
(see greenhouse.py / lever.py / billing.py) of implementing the vendor's
documented REST shape via `httpx` directly rather than a vendor SDK.

Why PayScale over the alternatives actually considered:
  - levels.fyi has no official public/documented API — only unofficial
    scrapers, which would carry the exact "no generic public endpoint"
    problem this repo's `workday.py` integration already declined to build
    against (see that module's docstring). Scraping a UI that can change or
    ban a scraper at any time is not a foundation for an attested metric.
  - A UK ONS/ASHE dataset is genuinely free and public, but it's occupation-
    code + region granular rather than job-title granular, and GBP/UK-only —
    a poor fit for the USD/US-tech offers this product is built around (every
    example in PAYLOADS.md and CLAUDE.md is a US company/USD offer).
  - PayScale's Compensation API is job-title + location granular, matching
    what Offer Check actually has (`CompetingOffer.role`), and USD-native.

Caveat, same as billing.py's Stripe integration and greenhouse.py/lever.py:
PayScale's Compensation API is commercial/sales-gated (not a simple self-serve
API-key signup like Stripe) and the request/response shape below has NOT been
exercised against a live PayScale account in this environment — confirm
against current PayScale API docs before relying on it in production.

fetch_market_range() never raises. A missing API key, an unmatched
role/location, a timeout, or any other failure all return None — this is
strictly best-effort. Offer Check's core guarantees (a working negotiation
and a TDX attestation over the outcome) never depend on a third party being
up. See CLAUDE.md's Offer Check Architecture section for how this composes
with `negotiation.market_percentile` and `routes.py::_maybe_attest`.
"""
import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_PAYSCALE_API_BASE = "https://api.payscale.com/v1"

# Offer Check doesn't currently capture candidate/role location anywhere in
# CompetingOffer or Session — see CLAUDE.md's "Known limitations" note for
# this feature. Callers without a real location fall back to this constant
# for a national-average comparison rather than skipping the lookup entirely.
DEFAULT_LOCATION = "United States"


@dataclass
class MarketRange:
    """p25/p50/p75 base-salary comparators for a role/level/location — the
    shape PayScale's Compensation API exposes. Never serialized to any API
    response or attested payload directly — only the derived percentile
    (see negotiation.market_percentile) crosses that boundary, same privacy
    discipline as opening_employer_offer never appearing in attested_terms()."""
    p25: float
    p50: float
    p75: float
    source: str = "payscale"


class MarketDataNotConfigured(Exception):
    """Raised internally when MARKET_DATA_API_KEY is unset — always caught within this module."""


_cache: dict[tuple[str, str | None, str], MarketRange | None] = {}


def _cache_key(role: str, level: str | None, location: str) -> tuple[str, str | None, str]:
    return (role.strip().lower(), level.strip().lower() if level else None, location.strip().lower())


async def fetch_market_range(role: str, level: str | None, location: str) -> MarketRange | None:
    """
    Looks up p25/p50/p75 base-salary comparators for role/level/location.

    In-memory cached per (role, level, location) — the same combination
    repeats across sessions, and this is a network call we want off the hot
    path (see routes.py::_maybe_attest, which calls this at most once per
    session, only once it reaches AGREED).

    Best-effort only — see module docstring. Returns None on any failure
    (unconfigured, unmatched role, timeout, malformed response) rather than
    raising, so a negotiation or attestation never blocks on this.
    """
    key = _cache_key(role, level, location)
    if key in _cache:
        return _cache[key]

    result = await _fetch_uncached(role, level, location)
    _cache[key] = result
    return result


async def _fetch_uncached(role: str, level: str | None, location: str) -> MarketRange | None:
    try:
        if not settings.market_data_api_key:
            raise MarketDataNotConfigured("MARKET_DATA_API_KEY is not set — market comparison is disabled")

        async with httpx.AsyncClient(
            base_url=_PAYSCALE_API_BASE,
            headers={"Authorization": f"Bearer {settings.market_data_api_key}"},
        ) as client:
            response = await client.get(
                "/compensation/salary-range",
                params={"job_title": role, "level": level or "", "location": location},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

        return MarketRange(
            p25=float(data["percentile_25"]),
            p50=float(data["percentile_50"]),
            p75=float(data["percentile_75"]),
        )
    except MarketDataNotConfigured as exc:
        logger.info(f"market data lookup skipped for {role!r}/{level!r}/{location!r}: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 — deliberately broad: this must NEVER raise, see module docstring
        logger.warning(f"market data lookup failed for {role!r}/{level!r}/{location!r} (non-fatal): {exc}")
        return None


def reset_cache() -> None:
    """Test-only: clear the in-memory lookup cache between test cases."""
    _cache.clear()
