"""
IP-based rate limiting — closes a real gap found while prepping the Phase 2C
Phala deploy (not hypothetical): POST /sessions is intentionally open, no
login, per the original Phase 1 spec — but its response hands back BOTH
candidate_token and employer_token. That means a script can, with zero
credential: create a session, seal an employer band with the token it just
received, then call start-agentic with the candidate token — all
self-authorized. demo_auth.py's magic-link gate only checks "does this
caller hold a valid token for this session," which a self-issued token
trivially satisfies. demo_auth's 15-call spend cap is per-session, so a
fresh session resets it every time. Neither stops unbounded session
creation -> unbounded real Claude spend.

This module is the missing layer: bound how many sessions and how many
agentic-negotiation calls a single IP can make per hour. It does not
replace setting a hard budget limit on the Anthropic API key itself in the
Anthropic console — that's the backstop that holds regardless of any bug
here, and it's out of this code's reach.

In-memory, ephemeral, lost on restart — same precedent as every other store
in this vertical (demo_auth's consumed-token set, spend-cap counters, the
session store itself). Limits are hardcoded, not env-var-driven, so this
fix doesn't require any new Phala dashboard entries — only a rebuilt image.
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request

WINDOW_SECONDS = 3600  # 1 hour

SESSION_CREATE_LIMIT = 10   # new sessions per IP per hour
AGENTIC_CALL_LIMIT = 5      # start-agentic(-package) calls per IP per hour
PROVENANCE_VERIFY_LIMIT = 3   # candidate/verify-credential calls per IP per hour — matches
                               # app.devcred's own 3/hour /evaluate limit, not its 10/hour
                               # /ingest limit: app.offercheck.provenance.verify_git_provenance
                               # runs the full two-layer pipeline (GitHub fetch + a paid
                               # GitEvaluatorAgent Claude call), so this endpoint has the same
                               # cost profile as devcred's LLM-calling endpoint, not its
                               # free-tier-only one. This endpoint is candidate-token-gated
                               # but, per this module's own docstring, a candidate token can
                               # be self-issued via POST /sessions with zero credential, so it
                               # gets the same per-IP backstop as session creation and agentic
                               # calls.
PARSE_OFFER_LETTER_LIMIT = 3  # /parse-offer-letter calls per IP per hour — this endpoint has
                               # NO auth at all (not even a party token — it isn't bound to a
                               # session yet), so it's the least-gated Claude-calling endpoint
                               # in this vertical. Matches PROVENANCE_VERIFY_LIMIT: single paid
                               # Claude call per hit, same cost profile.
MOVE_LIMIT = 20              # candidate/move + employer/move calls per IP per hour — no Claude
                               # cost here, so this is a griefing backstop (a party-token holder
                               # scripting instant round-burning to force premature expiry), not
                               # a spend backstop. Looser than the Claude-calling limits above
                               # since 5 legitimate rounds of back-and-forth between two humans
                               # sharing one NAT/IP is a real scenario this must not block.
COMPANY_REGISTER_LIMIT = 5   # /company/register calls per IP per hour — unauthenticated by
                               # design (it's the signup endpoint, there's no API key yet), so
                               # it had zero backstop before this. No Claude cost, but unlimited
                               # signups grow auth.py's in-memory Company store without bound and
                               # each one mints a fresh API key that unlocks bulk_verify below.
BULK_VERIFY_LIMIT = 3        # /company/verify/bulk calls per IP per hour — deliberately a
                               # call-count bucket, NOT scaled per session created. Each call can
                               # create up to 50 sessions (BulkVerifyRequest.max_length), so
                               # reusing SESSION_CREATE_LIMIT's 10/hour bucket per-session would
                               # make a single legitimate 50-candidate bulk call impossible. This
                               # bucket instead caps repeated bulk calls (worst case ~150
                               # sessions/hour/IP) independent of the plain /sessions bucket,
                               # closing "many session/token pairs with zero backstop" without
                               # breaking the documented "up to 50 per call" feature.
DISPUTE_LIMIT = 10           # employer/dispute + candidate/dispute calls per IP per hour — same
                               # "no Claude cost, backstop against a self-issued-token script" family
                               # as MOVE_LIMIT, but its own bucket rather than sharing MOVE_LIMIT's:
                               # dispute filing and move-spam are different usage shapes (see
                               # app.offercheck.disputes.MAX_DISPUTES_PER_PARTY_PER_SESSION, which
                               # already hard-caps *legitimate* per-session filing at 3/party — this
                               # per-IP limit only needs to guard against a script filing disputes
                               # across many self-issued sessions, not a real high-frequency human
                               # workflow the way MOVE_LIMIT's looser 20/hour is calibrated for).

_session_create_hits: dict[str, list[float]] = defaultdict(list)
_agentic_call_hits: dict[str, list[float]] = defaultdict(list)
_provenance_verify_hits: dict[str, list[float]] = defaultdict(list)
_parse_offer_letter_hits: dict[str, list[float]] = defaultdict(list)
_move_hits: dict[str, list[float]] = defaultdict(list)
_company_register_hits: dict[str, list[float]] = defaultdict(list)
_bulk_verify_hits: dict[str, list[float]] = defaultdict(list)
_dispute_hits: dict[str, list[float]] = defaultdict(list)


def reset() -> None:
    """Test-only: clear all rate-limit state between test cases."""
    _session_create_hits.clear()
    _agentic_call_hits.clear()
    _provenance_verify_hits.clear()
    _parse_offer_letter_hits.clear()
    _move_hits.clear()
    _company_register_hits.clear()
    _bulk_verify_hits.clear()
    _dispute_hits.clear()


def client_ip(request: Request) -> str:
    """
    Prefers X-Forwarded-For's first hop (the original client, if Phala's
    ingress sits in front of the container as a reverse proxy) over the
    direct socket peer. Confirm Phala actually sets this header in your
    deployment — if it doesn't, every request will appear to come from the
    proxy's own IP and this rate limiter will effectively apply globally
    rather than per-client. Worth checking after the first real deploy.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check(hits: dict[str, list[float]], key: str, limit: int) -> None:
    now = time.time()
    recent = [t for t in hits[key] if now - t < WINDOW_SECONDS]
    if len(recent) >= limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded — try again later")
    recent.append(now)
    hits[key] = recent


def check_session_create(request: Request) -> None:
    _check(_session_create_hits, client_ip(request), SESSION_CREATE_LIMIT)


def check_agentic_call(request: Request) -> None:
    _check(_agentic_call_hits, client_ip(request), AGENTIC_CALL_LIMIT)


def check_provenance_verify(request: Request) -> None:
    _check(_provenance_verify_hits, client_ip(request), PROVENANCE_VERIFY_LIMIT)


def check_parse_offer_letter(request: Request) -> None:
    _check(_parse_offer_letter_hits, client_ip(request), PARSE_OFFER_LETTER_LIMIT)


def check_move(request: Request) -> None:
    _check(_move_hits, client_ip(request), MOVE_LIMIT)


def check_company_register(request: Request) -> None:
    _check(_company_register_hits, client_ip(request), COMPANY_REGISTER_LIMIT)


def check_bulk_verify(request: Request) -> None:
    _check(_bulk_verify_hits, client_ip(request), BULK_VERIFY_LIMIT)


def check_dispute(request: Request) -> None:
    _check(_dispute_hits, client_ip(request), DISPUTE_LIMIT)
