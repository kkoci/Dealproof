"""
Market-data integration — external salary comparator for a closed Offer Check
session. Sibling to `negotiation.final_gap_pct` (see that function's
docstring): final_gap_pct is a *relative* external anchor (did the number
move from the employer's own opening position); this is an *absolute* one
(does the final number look sane against real third-party comparators the
negotiating agent never had access to or control over).

Data sources: **BLS OEWS** (US, Bureau of Labor Statistics' Occupational
Employment and Wage Statistics survey) and **ONS ASHE** (UK, Office for
National Statistics' Annual Survey of Hours and Earnings). Both are free
and public with no sales process — this replaces an earlier PayScale-based
implementation, which turned out to be enterprise/sales-gated (no self-serve
API access at all) and therefore not viable to actually integrate. levels.fyi
was considered again for the same reason as before: no official public/
documented API, only unofficial scrapers — the same "no generic public
endpoint" problem `workday.py` already declined to build against.

**Accepted tradeoff, stated plainly, not glossed over:** both BLS and ONS are
occupation-code + region granular, not job-title + seniority-level granular.
"Senior Backend Engineer" maps to the same BLS/ONS bucket as any other
software-development role at any seniority — the wage *percentile* still
carries real signal (a $400K base will show up near the top of that bucket's
distribution regardless), but this is coarser than a paid, job-title-precise
source would be. `fetch_market_range`'s signature and `MarketRange`'s shape
are deliberately unchanged from the PayScale version specifically so a more
granular paid source can be swapped in later — routes.py, negotiation.py,
schemas.py, and store.py never need to know which source answered the call.

Source selection (see `fetch_market_range`): BLS for USD offers, ONS for GBP
offers. Offer Check doesn't currently capture currency OR location anywhere
on `CompetingOffer`/`Session` (same known gap flagged in the previous pass),
so in practice every call today passes the module's USD/`DEFAULT_LOCATION`
defaults and BLS is the only source actually exercised in production until
that's added — ONS is fully implemented and tested, just currently unreached
by any real caller. Both source functions also default to a *national*
aggregate area code (`0000000` for BLS, `K02000001` for ONS — see each
function's docstring) for the same reason: no real location signal exists to
route to a specific metro/region yet.

Occupation-code mapping: both surveys use an SOC (Standard Occupational
Classification) code, but **US SOC and UK SOC are different taxonomies that
happen to share an acronym** — do not treat a US SOC code as valid input to
ONS or vice versa. `_map_role_to_bls_soc` / `_map_role_to_ons_soc` are small,
deliberately non-exhaustive keyword lookup tables covering common tech
roles; anything unmapped returns `None` (never raises), which propagates all
the way out as `market_percentile: None` — see the module-level resilience
note below.

Caveat, same convention as every other external integration in this repo
(billing.py's Stripe call, greenhouse.py, lever.py, and the PayScale version
this replaces): the exact request/response shapes below are a best-effort
implementation of each vendor's documented API conventions, **not** exercised
against a live BLS or ONS query in this environment. In particular: BLS's
OEWS series-ID construction (survey/seasonal/area-type/area/industry/
occupation/datatype segments) and its per-percentile datatype codes, and
ONS's dataset/edition/version path and dimension-label shape for ASHE, should
both be confirmed against current developer docs (bls.gov/developers,
bls.gov/help/hlpforma.htm#OE, and api.ons.gov.uk) before relying on this in
production. The occupation-code tables should likewise be checked against
the current BLS SOC and ONS SOC indexes.

fetch_market_range() and its two source-specific functions never raise. A
missing/invalid key, an unmapped role, a timeout, or any other failure all
return None — this is strictly best-effort. Offer Check's core guarantees (a
working negotiation and a TDX attestation over the outcome) never depend on
a third party being up. See CLAUDE.md's Offer Check Architecture section for
how this composes with `negotiation.market_percentile` and
`routes.py::_maybe_attest`.
"""
import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Offer Check doesn't currently capture candidate/role location or currency
# anywhere in CompetingOffer or Session — see module docstring's "Accepted
# tradeoff" note. Callers without real data fall back to these constants.
DEFAULT_LOCATION = "United States"
DEFAULT_CURRENCY = "USD"


@dataclass
class MarketRange:
    """p25/p50/p75 wage comparators for a role/location, from either BLS OEWS
    (currency="USD") or ONS ASHE (currency="GBP"). Never serialized to any API
    response or attested payload directly — only the derived percentile (see
    negotiation.market_percentile) crosses that boundary, same privacy
    discipline as opening_employer_offer never appearing in attested_terms()."""
    p25: float
    p50: float
    p75: float
    source: str = "bls"  # "bls" | "ons"
    currency: str = "USD"  # "USD" | "GBP"


# Shared in-memory cache across both sources, keyed by (source, role, location)
# per the module's own resilience contract — the same combination repeats
# across sessions, and this is a network call we want off the hot path (see
# routes.py::_maybe_attest, which calls this at most once per session, only
# once it reaches AGREED).
_cache: dict[tuple[str, str, str], MarketRange | None] = {}


def _cache_key(source: str, role: str, location: str) -> tuple[str, str, str]:
    return (source, role.strip().lower(), location.strip().lower())


def reset_cache() -> None:
    """Test-only: clear the in-memory lookup cache between test cases."""
    _cache.clear()


# ---------------------------------------------------------------------------
# BLS OEWS (US) — role -> SOC code mapping
# ---------------------------------------------------------------------------

# Deliberately non-exhaustive — common tech roles only, matched by keyword
# against a lowercased free-text role string. Anything unmapped returns None
# from _map_role_to_bls_soc, which propagates out as market_percentile: None.
# Confirm these against the current BLS SOC index (bls.gov/soc) before
# relying on them in production — some (e.g. "product manager") are genuine
# approximations since BLS has no dedicated code for that role.
_BLS_SOC_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("software engineer", "software developer", "backend engineer", "backend developer",
      "frontend engineer", "frontend developer", "full stack", "full-stack", "mobile engineer",
      "ios engineer", "android engineer"), "15-1252"),   # Software Developers
    (("data scientist", "machine learning engineer", "ml engineer", "ai engineer"), "15-2051"),  # Data Scientists
    (("data engineer", "database architect", "database administrator"), "15-1245"),  # Database Architects
    (("devops", "site reliability", " sre", "sre ", "platform engineer",
      "infrastructure engineer", "systems administrator"), "15-1244"),  # Network and Computer Systems Administrators
    (("security engineer", "security analyst", "infosec"), "15-1212"),  # Information Security Analysts
    (("qa engineer", "quality assurance", "test engineer", "sdet"), "15-1253"),  # Software QA Analysts and Testers
    (("engineering manager", "director of engineering", "vp of engineering",
      "head of engineering", "cto", "it manager"), "11-3021"),  # Computer and Information Systems Managers
    (("product manager", "product owner"), "11-9199"),  # Managers, All Other — approximate, no dedicated BLS code
    (("data analyst", "business analyst", "business intelligence"), "13-1111"),  # Management Analysts — approximate
)


def _map_role_to_bls_soc(role: str) -> str | None:
    normalized = f" {role.strip().lower()} "
    for keywords, soc_code in _BLS_SOC_KEYWORDS:
        if any(kw in normalized for kw in keywords):
            return soc_code
    if any(kw in normalized for kw in ("engineer", "developer", "programmer")):
        return "15-1299"  # Computer Occupations, All Other — generic tech-role fallback
    return None


# ---------------------------------------------------------------------------
# ONS ASHE (UK) — role -> SOC code mapping
# ---------------------------------------------------------------------------

# Same discipline as the BLS table above, over UK SOC codes (SOC2010 4-digit,
# as historically published by ASHE) — confirm against the current ONS SOC
# index (ons.gov.uk SOC hierarchy) before relying on these in production.
# US SOC and UK SOC are different taxonomies; codes are NOT interchangeable
# with the BLS table above despite the shared "SOC" name.
_ONS_SOC_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("software engineer", "software developer", "backend engineer", "backend developer",
      "frontend engineer", "frontend developer", "full stack", "full-stack",
      "programmer", "mobile engineer", "ios engineer", "android engineer"), "2136"),  # Programmers and software development professionals
    (("data engineer", "data architect", "database"), "2135"),  # IT business analysts, architects and systems designers — approximate
    (("devops", "site reliability", " sre", "sre ", "platform engineer",
      "infrastructure engineer", "systems administrator", "security engineer",
      "security analyst", "infosec", "qa engineer", "quality assurance",
      "test engineer", "sdet"), "2139"),  # IT and telecommunications professionals n.e.c. — approximate
    (("engineering manager", "director of engineering", "vp of engineering",
      "head of engineering", "cto", "it manager"), "2133"),  # IT specialist managers
    (("data scientist", "machine learning engineer", "ml engineer", "ai engineer",
      "data analyst", "business analyst", "business intelligence", "product manager",
      "product owner"), "2425"),  # Actuaries, economists and statisticians — approximate, no closer UK SOC fit
)


def _map_role_to_ons_soc(role: str) -> str | None:
    normalized = f" {role.strip().lower()} "
    for keywords, soc_code in _ONS_SOC_KEYWORDS:
        if any(kw in normalized for kw in keywords):
            return soc_code
    if any(kw in normalized for kw in ("engineer", "developer", "programmer")):
        return "2136"  # Programmers and software development professionals — generic tech-role fallback
    return None


# ---------------------------------------------------------------------------
# BLS OEWS fetch
# ---------------------------------------------------------------------------

_BLS_API_BASE = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
_BLS_NATIONAL_AREA_CODE = "0000000"  # OEWS area code for the US national aggregate


async def fetch_market_range_bls(role: str, location: str) -> MarketRange | None:
    """
    US wage comparator via BLS OEWS. Best-effort only — see module docstring
    for the series-ID construction caveat. Never raises; unmapped role, no
    API access, timeout, or malformed response all return None.

    `location` is currently unused beyond cache-key scoping — this only ever
    queries the national aggregate (`_BLS_NATIONAL_AREA_CODE`), since Offer
    Check has no real per-session location data yet (see module docstring).
    """
    cache_key = _cache_key("bls", role, location)
    if cache_key in _cache:
        return _cache[cache_key]
    result = await _fetch_bls_uncached(role)
    _cache[cache_key] = result
    return result


async def _fetch_bls_uncached(role: str) -> MarketRange | None:
    soc_code = _map_role_to_bls_soc(role)
    if soc_code is None:
        logger.info(f"BLS market lookup skipped — no SOC-code mapping for role {role!r}")
        return None

    try:
        # OEWS series ID format (BLS "OE" survey — bls.gov/help/hlpforma.htm#OE):
        # OEU + seasonal(U=unadjusted) + area-type(N=national) + area-code(7)
        #     + industry-code(6, "000000"=cross-industry) + occupation-code(6, SOC without the hyphen)
        #     + datatype-code(2). Datatype codes used here (10=annual 25th percentile wage,
        # 12=annual median wage, 14=annual 75th percentile wage) are BLS's commonly documented
        # OEWS datatype codes as of this writing — confirm against current BLS OEWS
        # documentation before relying on this in production (see module docstring).
        soc_digits = soc_code.replace("-", "")
        datatype_codes = {"10": "p25", "12": "p50", "14": "p75"}
        series_ids = [
            f"OEUN{_BLS_NATIONAL_AREA_CODE}000000{soc_digits}{dt}" for dt in datatype_codes
        ]

        body = {"seriesid": series_ids, "startyear": "2023", "endyear": "2024"}
        if settings.bls_api_key:
            body["registrationkey"] = settings.bls_api_key

        async with httpx.AsyncClient(base_url=_BLS_API_BASE) as client:
            response = await client.post("", json=body, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "REQUEST_SUCCEEDED":
            raise ValueError(f"BLS API returned status {data.get('status')!r}")

        values: dict[str, float] = {}
        for series in data["Results"]["series"]:
            series_id = series["seriesID"]
            dt_code = series_id[-2:]
            label = datatype_codes[dt_code]
            latest_period = series["data"][0]  # most recent period listed first, per BLS API convention
            values[label] = float(latest_period["value"])

        return MarketRange(p25=values["p25"], p50=values["p50"], p75=values["p75"], source="bls", currency="USD")
    except Exception as exc:  # noqa: BLE001 — deliberately broad: this must NEVER raise, see module docstring
        logger.warning(f"BLS market lookup failed for {role!r} (non-fatal): {exc}")
        return None


# ---------------------------------------------------------------------------
# ONS ASHE fetch
# ---------------------------------------------------------------------------

_ONS_API_BASE = "https://api.ons.gov.uk/dataset/ashe-tables-7/editions/time-series/versions/1/observations"
_ONS_UK_AREA_CODE = "K02000001"  # ONS/GSS geography code for "United Kingdom" as a whole


async def fetch_market_range_ons(role: str, location: str) -> MarketRange | None:
    """
    UK wage comparator via ONS ASHE. Best-effort only — see module docstring
    for the dataset/dimension-shape caveat. Never raises; unmapped role, no
    network access, timeout, or malformed response all return None.

    `location` is currently unused beyond cache-key scoping — this only ever
    queries the UK-wide aggregate (`_ONS_UK_AREA_CODE`), since Offer Check
    has no real per-session location data yet (see module docstring).
    """
    cache_key = _cache_key("ons", role, location)
    if cache_key in _cache:
        return _cache[cache_key]
    result = await _fetch_ons_uncached(role)
    _cache[cache_key] = result
    return result


async def _fetch_ons_uncached(role: str) -> MarketRange | None:
    soc_code = _map_role_to_ons_soc(role)
    if soc_code is None:
        logger.info(f"ONS market lookup skipped — no SOC-code mapping for role {role!r}")
        return None

    try:
        # ONS API dataset-observations shape (api.ons.gov.uk) — dataset id, edition, and
        # dimension names below are a best-effort match to ASHE's published structure as
        # of this writing, not exercised against a live query. Confirm against the current
        # ONS API docs / ASHE dataset definition before relying on this in production.
        async with httpx.AsyncClient(base_url=_ONS_API_BASE) as client:
            response = await client.get(
                "",
                params={
                    "geography": _ONS_UK_AREA_CODE,
                    "occupation": soc_code,
                    "sex": "all",
                    "workingpattern": "all",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

        observations = {
            obs["dimensions"]["statistics"]["label"]: float(obs["observation"])
            for obs in data["observations"]
        }
        return MarketRange(
            p25=observations["25th percentile"],
            p50=observations["Median"],
            p75=observations["75th percentile"],
            source="ons",
            currency="GBP",
        )
    except Exception as exc:  # noqa: BLE001 — deliberately broad: this must NEVER raise, see module docstring
        logger.warning(f"ONS market lookup failed for {role!r} (non-fatal): {exc}")
        return None


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

async def fetch_market_range(
    role: str, level: str | None, location: str, currency: str = DEFAULT_CURRENCY
) -> MarketRange | None:
    """
    Picks a source by `currency` and delegates: "GBP" -> ONS ASHE, anything
    else (including the default "USD") -> BLS OEWS. See module docstring for
    why this is the whole of the selection logic today — Offer Check has no
    real per-session currency/location signal yet, so every current caller
    passes the module defaults and BLS is the only source actually reached
    in production until that changes.

    `level` is accepted for signature stability with callers/tests but is
    NOT used for occupation-code selection — neither BLS's nor ONS's SOC
    taxonomy is seniority-stratified; seniority differences show up in the
    wage percentile spread itself (see negotiation.market_percentile), not
    in which occupation bucket a role maps to.
    """
    if currency.strip().upper() == "GBP":
        return await fetch_market_range_ons(role, location)
    return await fetch_market_range_bls(role, location)
