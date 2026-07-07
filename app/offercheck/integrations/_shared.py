"""Shared helpers for ATS integrations — Phase 3."""
import hashlib
import hmac


class AtsNotConfigured(Exception):
    """Base class for 'this company hasn't connected this ATS' errors."""


def verify_hmac_signature(raw_body: bytes, provided_signature_hex: str, secret: str) -> bool:
    """
    Generic HMAC-SHA256 webhook signature check: compute over the raw request
    body with the per-company webhook_secret, compare in constant time.

    This is the standard shape used by most webhook providers (a hex digest
    of HMAC-SHA256 over the raw body). The exact header name and any prefix
    (e.g. "sha256=") are vendor-specific — confirm against the current vendor
    docs before wiring a real webhook; this function only checks the digest.
    """
    if not provided_signature_hex:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided_signature_hex.strip().lower())
