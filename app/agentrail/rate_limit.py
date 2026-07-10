"""
IP-based rate limiting for Agent Rail — same pattern as app/offercheck/rate_limit.py
(there is no slowapi anywhere in this repo; this hand-rolled, in-memory, no-dependency
sliding-window limiter is the actual existing pattern, not slowapi).

Kept as a small standalone module rather than importing from app.offercheck.rate_limit:
that module's limits (SESSION_CREATE_LIMIT, AGENTIC_CALL_LIMIT) and hit-dicts are
private and product-specific, and cross-importing another vertical's internals would
couple two products meant to stay standalone (see feedback-vertical-nav guidance).
The *mechanism* — client_ip() + sliding-window check — is duplicated verbatim; the
*limit value* (DEAL_CREATE_LIMIT) is Agent Rail's own.

This is a backstop, not the primary gate — app.offercheck.demo_auth's magic-link
token check (see app/agentrail/routes.py's _authorize_deal_creation) is the primary
gate on POST /deals. This catches what a single-use token check alone wouldn't: e.g.
someone hammering the endpoint with many freshly-minted tokens.

In-memory, ephemeral, lost on restart — consistent with every other store in this
module (app/agentrail/store.py, demo_auth's consumed-token set and spend-cap counters).
"""
import time
from collections import defaultdict

from fastapi import HTTPException, Request

WINDOW_SECONDS = 3600  # 1 hour

DEAL_CREATE_LIMIT = 3  # POST /deals calls per IP per hour

_deal_create_hits: dict[str, list[float]] = defaultdict(list)


def reset() -> None:
    """Test-only: clear all rate-limit state between test cases."""
    _deal_create_hits.clear()


def client_ip(request: Request) -> str:
    """Prefers X-Forwarded-For's first hop over the direct socket peer — see
    app/offercheck/rate_limit.py's client_ip() for the reverse-proxy caveat,
    which applies identically here."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_deal_create(request: Request) -> None:
    now = time.time()
    key = client_ip(request)
    recent = [t for t in _deal_create_hits[key] if now - t < WINDOW_SECONDS]
    if len(recent) >= DEAL_CREATE_LIMIT:
        raise HTTPException(status_code=429, detail="rate limit exceeded — try again later")
    recent.append(now)
    _deal_create_hits[key] = recent
