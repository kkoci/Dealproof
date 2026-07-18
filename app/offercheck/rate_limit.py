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
PROVENANCE_VERIFY_LIMIT = 10  # candidate/verify-credential calls per IP per hour — same
                               # order of magnitude as app.devcred's own 10/hour ingest
                               # limiter for the identical GitHub-fetch pipeline; this
                               # endpoint is candidate-token-gated but, per this module's
                               # own docstring, a candidate token can be self-issued via
                               # POST /sessions with zero credential, so it gets the same
                               # per-IP backstop as session creation and agentic calls.

_session_create_hits: dict[str, list[float]] = defaultdict(list)
_agentic_call_hits: dict[str, list[float]] = defaultdict(list)
_provenance_verify_hits: dict[str, list[float]] = defaultdict(list)


def reset() -> None:
    """Test-only: clear all rate-limit state between test cases."""
    _session_create_hits.clear()
    _agentic_call_hits.clear()
    _provenance_verify_hits.clear()


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
