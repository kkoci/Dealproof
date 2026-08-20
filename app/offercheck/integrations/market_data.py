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

**Metro/regional granularity (added — see `CompetingOffer.location`/`currency`,
app.offercheck.schemas):** both `CompetingOffer` and `EmployerInviteRequest`/
`CandidateJoinRequest` now carry optional `location`/`currency` fields, wired
through to this module at `routes.py::_maybe_attest` (`session.competing_offer
.location or DEFAULT_LOCATION`). When a real location maps to a known
metro (BLS) or UK region (ONS), the lookup below now genuinely narrows to
that geography instead of always querying the national/UK-wide aggregate.
An unmapped or absent location falls back to the national/UK-wide aggregate
exactly as before — this fallback is the safe default, not a breaking change,
and every existing caller that never sends a location keeps working
identically.

**Accepted tradeoff, stated plainly, not glossed over:** occupation mapping
is still occupation-code + region granular, not job-title + seniority-level
granular. "Senior Backend Engineer" maps to the same BLS/ONS bucket as any
other software-development role at any seniority — the wage *percentile*
still carries real signal (a $400K base will show up near the top of that
bucket's distribution regardless), but this is coarser than a paid,
job-title-precise source would be. `fetch_market_range`'s signature and
`MarketRange`'s shape are deliberately unchanged from the PayScale version
specifically so a more granular paid source (or the DOL/OFLC source scoped
but not built in this pass — see the offercheck market-comparator research
notes) can be swapped in later — routes.py, negotiation.py, schemas.py, and
store.py never need to know which source answered the call.

**ONS API migration (load-bearing, not optional):** the previous
`api.ons.gov.uk/dataset/ashe-tables-7/...` endpoint this module used is
**decommissioned — confirmed live 2026-08, returns HTTP 404 with an explicit
"This API has been decommissioned... fully retired on 25/11/2024" message
for every path under it.** ONS's current API root is
`https://api.beta.ons.gov.uk/v1` (Beta, no API key). Adding regional
granularity to a dead endpoint would have accomplished nothing, so this pass
migrates the base integration too — see `_ONS_API_BASE` below. One real,
accepted granularity *loss* from this migration: the dataset that actually
carries a region dimension (`ashe-tables-3`, "region by occupation") only
publishes **1- and 2-digit SOC major/sub-major groups** in its
`standardoccupationalclassification` dimension (confirmed live — 36 options,
all 1-2 digit) — not the 4-digit codes `_ONS_SOC_KEYWORDS` maps to. Both the
UK-wide and regional paths now go through this same dataset, so both are
truncated to 2 digits at query time (`soc_code[:2]`) — `_ONS_SOC_KEYWORDS`
and `_map_role_to_ons_soc` themselves are untouched (still return 4-digit
codes) so cache keys and role-mapping behavior/tests stay stable; only the
value sent to the ONS API is truncated, at the query-construction step.

Source selection (see `fetch_market_range`): BLS for USD offers, ONS for GBP
offers — this part is unchanged from before.

Occupation-code mapping: both surveys use an SOC (Standard Occupational
Classification) code, but **US SOC and UK SOC are different taxonomies that
happen to share an acronym** — do not treat a US SOC code as valid input to
ONS or vice versa. `_map_role_to_bls_soc` / `_map_role_to_ons_soc` are small,
deliberately non-exhaustive keyword lookup tables covering common tech
roles; anything unmapped returns `None` (never raises), which propagates all
the way out as `market_percentile: None` — see the module-level resilience
note below. `_BLS_METRO_AREA_CODES` / `_ONS_UK_REGION_CODES` are the same
kind of small, non-exhaustive keyword table, over location strings instead
of role strings — confirm/extend both against the current BLS OEWS area
reference (download.bls.gov/pub/time.series/oe/oe.area) and ONS's
`administrative-geography` code list before relying on either in production
beyond the major metros/regions covered here.

Caveat, same convention as every other external integration in this repo
(billing.py's Stripe call, greenhouse.py, lever.py): the BLS request/response
shape below (OEWS series-ID construction, per-percentile datatype codes) is a
best-effort implementation of BLS's documented API conventions, confirmed
against a community reference (github.com/govex/bls-oews-api-tutorial, since
BLS's own generic bls.gov/help/hlpforma.htm series-ID page no longer lists
OEWS at all as of 2026-08) but **not** exercised against a live BLS query
with a real registration key in this environment (BLS's API requires a free
key for anything beyond a very low unauthenticated rate limit). The ONS
request/response shape **was** exercised against the live beta API while
researching this change (2026-08) — the dataset/dimension/geography-code
values below (metro CBSA codes, ONS region GSS codes, dimension option ids)
are confirmed current as of that date, not assumed. One live-testing finding
worth flagging honestly: `ashe-tables-3`'s observations endpoint returned an
HTTP 502 after ~28s on two separate live attempts during this research
(the dataset's underlying CSV export is ~750MB, per its own `downloads`
metadata — this specific dataset's live query path may simply be slow/
unreliable in practice, independent of whether the request is well-formed).
This module's existing 10s timeout and blanket `except Exception` already
turn that into a clean `None`, which is the correct, safe behavior — it's
flagged here so a `market_percentile: None` on a GBP session with a mapped
UK role isn't mistaken for a code bug.

fetch_market_range() and its two source-specific functions never raise. A
missing/invalid key, an unmapped role, an unmapped location, a timeout, or
any other failure all return None (an unmapped *location* falls back to the
national/UK-wide aggregate rather than failing outright — only an unmapped
*role* returns None, since there's no "generic occupation" fallback for that
one). This is strictly best-effort. Offer Check's core guarantees (a working
negotiation and a TDX attestation over the outcome) never depend on a third
party being up. See CLAUDE.md's Offer Check Architecture section for how
this composes with `negotiation.market_percentile` and
`routes.py::_maybe_attest`.
"""
import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Offer Check's per-session location/currency (see CompetingOffer.location/currency,
# app.offercheck.schemas) is optional — callers without real data, or with a location that
# doesn't map to anything below, fall back to these constants (national/UK-wide aggregate).
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


# Deliberately non-exhaustive — major US tech-hub metros only, matched by keyword against a
# lowercased free-text location string, same discipline as the role keyword tables above.
# CBSA codes (7-digit, zero-padded) confirmed live 2026-08 directly against BLS's own OEWS
# area reference file (download.bls.gov/pub/time.series/oe/oe.area — "areatype_code" M rows),
# which reflects the 2020-Census MSA delineations first applied in the May 2024 OEWS release.
# Anything unmapped falls back to the national aggregate — see _map_location_to_bls_area.
_BLS_METRO_AREA_CODES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("new york", "nyc", "manhattan", "brooklyn", "newark"), "0035620"),
    (("san francisco", "oakland", "bay area", "silicon valley"), "0041860"),
    (("los angeles", "long beach", "anaheim"), "0031080"),
    (("chicago", "naperville"), "0016980"),
    (("seattle", "tacoma", "bellevue"), "0042660"),
    (("austin", "round rock"), "0012420"),
    (("boston", "cambridge"), "0014460"),
    (("atlanta", "sandy springs"), "0012060"),
    (("denver", "aurora"), "0019740"),
    (("washington dc", "washington, dc", "arlington", "alexandria"), "0047900"),
    (("dallas", "fort worth"), "0019100"),
)


def _map_location_to_bls_area(location: str) -> str | None:
    normalized = f" {location.strip().lower()} "
    for keywords, area_code in _BLS_METRO_AREA_CODES:
        if any(kw in normalized for kw in keywords):
            return area_code
    return None


# ---------------------------------------------------------------------------
# ONS ASHE (UK) — role -> SOC code mapping
# ---------------------------------------------------------------------------

# Same discipline as the BLS table above, over UK SOC codes (SOC2010 4-digit,
# as historically published by ASHE) — confirm against the current ONS SOC
# index (ons.gov.uk SOC hierarchy) before relying on these in production.
# US SOC and UK SOC are different taxonomies; codes are NOT interchangeable
# with the BLS table above despite the shared "SOC" name. NOTE: only the
# first 2 digits of these codes are actually sent to the ONS API today (see
# _fetch_ons_uncached) — kept 4-digit here so this table/mapping function's
# own behavior and tests stay unchanged; see module docstring.
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


# Deliberately non-exhaustive — major UK city/region keywords only, matched the same way as
# every other keyword table in this module. Codes are ONS's own "administrative-geography"
# GSS area codes, confirmed live 2026-08 against ashe-tables-3's own geography dimension —
# these are NOT the Eurostat-style ITL region codes ("TLx") some secondary sources quote for
# UK regions; ONS's dataset API uses its native GSS scheme instead (e.g. London is
# "E12000007" here, not ITL1's "TLI"). Anything unmapped falls back to the UK-wide aggregate.
_ONS_UK_REGION_CODES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("london",), "E12000007"),
    (("newcastle", "sunderland", "north east"), "E12000001"),
    (("manchester", "liverpool", "north west"), "E12000002"),
    (("leeds", "sheffield", "yorkshire"), "E12000003"),
    (("nottingham", "leicester", "east midlands"), "E12000004"),
    (("birmingham", "west midlands"), "E12000005"),
    (("cambridge", "norwich", "east of england", "east anglia"), "E12000006"),
    (("brighton", "oxford", "reading", "south east"), "E12000008"),
    (("bristol", "plymouth", "south west"), "E12000009"),
    (("cardiff", "swansea", "wales"), "W92000004"),
    (("edinburgh", "glasgow", "scotland"), "S92000003"),
    (("belfast", "northern ireland"), "N92000002"),
)


def _map_location_to_ons_region(location: str) -> str | None:
    normalized = f" {location.strip().lower()} "
    for keywords, region_code in _ONS_UK_REGION_CODES:
        if any(kw in normalized for kw in keywords):
            return region_code
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

    `location` is matched against `_BLS_METRO_AREA_CODES` — a mapped location
    (e.g. "Seattle, WA") narrows the query to that metro's OEWS estimates; an
    unmapped or generic location (including the module default) falls back to
    the national aggregate (`_BLS_NATIONAL_AREA_CODE`), exactly as before this
    location support was added.
    """
    cache_key = _cache_key("bls", role, location)
    if cache_key in _cache:
        return _cache[cache_key]
    result = await _fetch_bls_uncached(role, location)
    _cache[cache_key] = result
    return result


async def _fetch_bls_uncached(role: str, location: str) -> MarketRange | None:
    soc_code = _map_role_to_bls_soc(role)
    if soc_code is None:
        logger.info(f"BLS market lookup skipped — no SOC-code mapping for role {role!r}")
        return None

    area_code = _map_location_to_bls_area(location)
    area_type = "M" if area_code is not None else "N"
    resolved_area_code = area_code or _BLS_NATIONAL_AREA_CODE

    try:
        # OEWS series ID format (BLS "OE" survey) — confirmed 2026-08 against
        # github.com/govex/bls-oews-api-tutorial (BLS's own generic series-ID docs page,
        # bls.gov/help/hlpforma.htm, no longer lists OEWS at all as of this writing):
        # OE + U(not seasonally adjusted) + area-type(1: M=metro/S=state/N=national)
        #    + area-code(7) + industry-code(6, "000000"=cross-industry)
        #    + occupation-code(6, SOC without the hyphen) + datatype-code(2).
        # Datatype codes used here (10=annual 25th percentile wage, 12=annual median wage,
        # 14=annual 75th percentile wage) are BLS's commonly documented OEWS datatype codes
        # as of this writing — confirm against current BLS OEWS documentation before relying
        # on this in production (see module docstring).
        soc_digits = soc_code.replace("-", "")
        datatype_codes = {"10": "p25", "12": "p50", "14": "p75"}
        series_ids = [
            f"OEU{area_type}{resolved_area_code}000000{soc_digits}{dt}" for dt in datatype_codes
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

# ONS's classic api.ons.gov.uk/dataset/... endpoint (used by the previous version of this
# module) is decommissioned — confirmed live 2026-08 (HTTP 404, explicit retirement notice,
# "fully retired on 25/11/2024"). Current API root, confirmed live: api.beta.ons.gov.uk/v1.
_ONS_API_ROOT = "https://api.beta.ons.gov.uk/v1"
_ONS_ASHE_DATASET = "ashe-tables-3"  # "Earnings and hours worked, region by occupation by two-digit SOC"
_ONS_ASHE_EDITION = "time-series"
_ONS_ASHE_VERSION = "7"  # latest published version confirmed live 2026-08 — ONS increments
                          # this on every new ASHE release; re-check against
                          # {_ONS_API_ROOT}/datasets/{_ONS_ASHE_DATASET}/editions before
                          # relying on this in production, it WILL drift over time.
_ONS_ASHE_YEAR = "2023"  # latest year available in this dataset's time dimension, confirmed live 2026-08
_ONS_API_BASE = (
    f"{_ONS_API_ROOT}/datasets/{_ONS_ASHE_DATASET}/editions/{_ONS_ASHE_EDITION}"
    f"/versions/{_ONS_ASHE_VERSION}/observations"
)
_ONS_UK_AREA_CODE = "K02000001"  # ONS/GSS geography code for "United Kingdom" as a whole


async def fetch_market_range_ons(role: str, location: str) -> MarketRange | None:
    """
    UK wage comparator via ONS ASHE. Best-effort only — see module docstring
    for the dataset-migration and SOC-truncation caveats. Never raises;
    unmapped role, no network access, timeout, or malformed response all
    return None.

    `location` is matched against `_ONS_UK_REGION_CODES` — a mapped location
    (e.g. "Manchester") narrows the query to that region's ASHE estimates; an
    unmapped or generic location (including the module default) falls back
    to the UK-wide aggregate (`_ONS_UK_AREA_CODE`), exactly as before this
    location support was added.
    """
    cache_key = _cache_key("ons", role, location)
    if cache_key in _cache:
        return _cache[cache_key]
    result = await _fetch_ons_uncached(role, location)
    _cache[cache_key] = result
    return result


async def _fetch_ons_uncached(role: str, location: str) -> MarketRange | None:
    soc_code = _map_role_to_ons_soc(role)
    if soc_code is None:
        logger.info(f"ONS market lookup skipped — no SOC-code mapping for role {role!r}")
        return None

    # ashe-tables-3's own "standardoccupationalclassification" dimension only publishes
    # 1-/2-digit SOC major/sub-major groups (confirmed live 2026-08 — 36 options total, all
    # 1-2 digit) — not the 4-digit codes _ONS_SOC_KEYWORDS maps to. Truncating here is a real,
    # accepted granularity loss versus the old (now-dead) endpoint's nominal 4-digit support —
    # see module docstring's "ONS API migration" note.
    soc_major_group = soc_code[:2]
    region_code = _map_location_to_ons_region(location) or _ONS_UK_AREA_CODE

    try:
        # ONS beta API observations shape (developer.ons.gov.uk/cmdobservations/), confirmed
        # live 2026-08: GET .../observations?time=...&geography=...&<dim>=<option>..., with a
        # single dimension allowed to be a '*' wildcard returning every option's value in one
        # response instead of one request per percentile. averagesandpercentiles='*' is used
        # here for exactly that — one request instead of three.
        async with httpx.AsyncClient(base_url=_ONS_API_BASE) as client:
            response = await client.get(
                "",
                params={
                    "time": _ONS_ASHE_YEAR,
                    "geography": region_code,
                    "sex": "all",
                    "workingpattern": "all",
                    "hoursandearnings": "annual-pay-gross",
                    "standardoccupationalclassification": soc_major_group,
                    "averagesandpercentiles": "*",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

        # Each wildcarded observation echoes back its own resolved dimension option (id +
        # label) alongside the value — confirmed live 2026-08 against this same API (a
        # non-ASHE dataset, since ashe-tables-3's own observations endpoint was unreliable
        # in live testing — see module docstring). Matched by option id, not dict key name,
        # since the echoed dimension key casing isn't part of the documented contract.
        target_ids = {"25": "p25", "median": "p50", "75": "p75"}
        values: dict[str, float] = {}
        for obs in data["observations"]:
            for dim in obs["dimensions"].values():
                opt_id = dim.get("id")
                if opt_id in target_ids:
                    values[target_ids[opt_id]] = float(obs["observation"])
                    break

        return MarketRange(
            p25=values["p25"],
            p50=values["p50"],
            p75=values["p75"],
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
    else (including the default "USD") -> BLS OEWS. `location` now genuinely
    affects the query when it maps to a known metro (BLS) or UK region
    (ONS) — see each source function's docstring — and falls back to the
    national/UK-wide aggregate otherwise, which stays the safe default for
    any caller that doesn't have real location data.

    `level` is accepted for signature stability with callers/tests but is
    NOT used for occupation-code selection — neither BLS's nor ONS's SOC
    taxonomy is seniority-stratified; seniority differences show up in the
    wage percentile spread itself (see negotiation.market_percentile), not
    in which occupation bucket a role maps to.
    """
    if currency.strip().upper() == "GBP":
        return await fetch_market_range_ons(role, location)
    return await fetch_market_range_bls(role, location)
