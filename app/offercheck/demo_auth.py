"""
Magic-link auth for Offer Check's Claude-calling endpoints.

SECURITY RULE (non-negotiable): every endpoint that triggers a Claude API
call must require a valid token before the handler runs. No exceptions.
Currently this is POST /sessions/{id}/start-agentic; any future
agent-calling endpoint must call require_authorized() (or equivalent) too.

# TODO: replace with TinyCloud OpenKey delegation when available (Sam's
# work) — this whole module is a deliberate 30-minute stopgap, not a real
# auth system. See "Do NOT build" in the originating request: no accounts,
# no email flows, no token database, no OAuth. Tokens are stateless HMACs;
# single-use and spend-cap bookkeeping is in-memory and does not survive a
# restart — acceptable for a stopgap, not for anything long-lived.

Two independent, layered protections:

1. Two ways to prove you're allowed to trigger start-agentic for a session:
     (a) a valid party token (candidate_token / employer_token — the
         existing per-session credential every real participant already
         has), or
     (b) a valid demo/magic-link token (HMAC-signed, time-boxed, single-use
         — minted via POST /auth/demo-link for sharing with a spectator who
         isn't a party to the negotiation, e.g. a prospect watching a demo).
   Either alone is sufficient — a party-token holder is already
   authenticated, so this isn't "AND both required": it's "prove you're
   authorized, by whichever legitimate means you have."

2. A hard per-session spend cap (15 Claude calls — 3 full 5-round
   negotiations) as a backstop independent of how the caller authenticated.
   The token should prevent abuse; this catches edge cases (e.g. someone
   re-triggering start-agentic on the same session many times with fresh
   party tokens, which the single-use demo-token check alone wouldn't catch
   since party tokens aren't single-use).

Magic-link tokens are stateless: `expires_at` is embedded in the token
itself and the HMAC is verified by recomputing it, so no lookup table is
needed to check validity. Only *consumption* (single-use) and the spend
cap need in-memory state, and both are intentionally ephemeral.
"""
import hashlib
import hmac
import logging
import time

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_EXPIRES_HOURS = 24.0
# Raised from 15: the approval-stage extension mechanism (negotiation.py's
# PENDING_APPROVAL/MAX_EXTENSIONS=3) can now trigger up to 3 additional full
# start-agentic calls on top of the original negotiation — up to 3 extensions x 5
# rounds each = 15 more calls alone, which the old cap didn't have headroom for. 40
# gives real headroom without removing the extension mechanism.
SPEND_CAP_PER_SESSION = 40


class InvalidToken(Exception):
    """Token missing, malformed, signature mismatch, or expired."""


class TokenAlreadyUsed(Exception):
    """Demo token has already been consumed once (single-use)."""


class SpendCapExceeded(Exception):
    """Session has made more Claude calls than SPEND_CAP_PER_SESSION allows."""


_CONSUMED_TOKENS: set[str] = set()
_CALL_COUNTS: dict[str, int] = {}


def reset() -> None:
    """Test-only: clear consumption + spend-cap state between test cases."""
    _CONSUMED_TOKENS.clear()
    _CALL_COUNTS.clear()


def require_secret_key_configured() -> None:
    """Called at app startup. Fails fast — no default, no silent bypass."""
    if not settings.offercheck_secret_key:
        raise RuntimeError(
            "OFFERCHECK_SECRET_KEY is not set. Offer Check's magic-link auth "
            "has no key to sign tokens with — refusing to start. Set "
            "OFFERCHECK_SECRET_KEY in the environment (e.g. "
            "`python -c \"import secrets; print(secrets.token_hex(32))\"`)."
        )


def warn_if_anthropic_keys_identical() -> None:
    """Called at app startup. Soft check — logs, does not block startup."""
    a, b = settings.offercheck_api_key, settings.anthropic_api_key
    if a and b and a == b:
        logger.warning(
            "OFFERCHECK_API_KEY is identical to ANTHROPIC_API_KEY — Offer Check "
            "is not actually using a separate Anthropic key. Set a distinct "
            "OFFERCHECK_API_KEY if you want offercheck usage tracked/limited "
            "independently of core DealProof's key."
        )


def _sign(session_id: str, expires_at: int) -> str:
    if not settings.offercheck_secret_key:
        raise RuntimeError("OFFERCHECK_SECRET_KEY is not set")
    payload = f"{session_id}:{expires_at}".encode()
    return hmac.new(settings.offercheck_secret_key.encode(), payload, hashlib.sha256).hexdigest()


def generate_token(session_id: str, expires_hours: float = DEFAULT_EXPIRES_HOURS) -> tuple[str, int]:
    """Returns (token, expires_at_unix_ts)."""
    expires_at = int(time.time() + expires_hours * 3600)
    signature = _sign(session_id, expires_at)
    return f"{expires_at}.{signature}", expires_at


def verify_token(session_id: str, token: str) -> int:
    """Returns expires_at on success; raises InvalidToken otherwise."""
    if not token or "." not in token:
        raise InvalidToken("malformed token")

    expires_at_str, _, signature = token.partition(".")
    try:
        expires_at = int(expires_at_str)
    except ValueError:
        raise InvalidToken("malformed token")

    expected = _sign(session_id, expires_at)
    if not hmac.compare_digest(expected, signature):
        raise InvalidToken("signature mismatch")
    if time.time() > expires_at:
        raise InvalidToken("token expired")

    return expires_at


def is_consumed(token: str) -> bool:
    return token in _CONSUMED_TOKENS


def consume(token: str) -> None:
    """Marks a demo token used. Idempotent-unsafe by design — callers must
    check is_consumed() first; calling consume() twice is a caller bug, not
    guarded here, since the single check-then-consume call site is trusted."""
    _CONSUMED_TOKENS.add(token)


def record_and_check_spend(session_id: str) -> None:
    """Increments this session's Claude-call counter; raises if it now
    exceeds the cap. Call once per actual Claude API call, before making it."""
    count = _CALL_COUNTS.get(session_id, 0) + 1
    _CALL_COUNTS[session_id] = count
    if count > SPEND_CAP_PER_SESSION:
        raise SpendCapExceeded(f"session {session_id} exceeded the {SPEND_CAP_PER_SESSION}-call spend cap")
