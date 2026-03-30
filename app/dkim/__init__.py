"""
DKIM email proof module — Phase 6 addition.

Provides TEE-internal DKIM signature verification for seller identity proofs.
The seller uploads a .eml file (base64-encoded). The TEE verifies the DKIM
signature via DNS lookup, extracts the sending domain, and injects a
TEE-verified credential into the seller agent's system prompt.

The email body is NEVER stored — only the verified domain name is retained.
"""
from app.dkim.verifier import DKIMResult, verify_email_proof

__all__ = ["DKIMResult", "verify_email_proof"]
