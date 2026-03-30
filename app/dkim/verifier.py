"""
DKIM email proof verifier — Phase 6.

Design
------
The seller submits a base64-encoded .eml file as `seller_email_eml` in the
DealCreate payload.  This module runs entirely inside the TEE and:

  1. Decodes the base64 payload to raw RFC-2822 email bytes.
  2. Extracts the `d=` tag from every DKIM-Signature header to identify the
     sending domain (e.g. "company.com").
  3. Calls dkimpy's `verify()` to perform a live DKIM signature check via DNS.
     If DNS is unavailable inside the CVM (network policy), the domain is still
     extracted and returned with `verified=False, dns_unavailable=True` so the
     UI can distinguish a verification failure from a network restriction.
  4. Returns a DKIMResult dataclass.  The raw email bytes are never logged or
     persisted — only the domain and verified flag leave this function.

Privacy guarantee
-----------------
The email body is discarded immediately after DKIM verification.  The only
information passed to the seller agent is:
  "[TEE-VERIFIED CREDENTIAL] seller represents <domain>"

Usage
-----
    from app.dkim.verifier import verify_email_proof

    result = await verify_email_proof(eml_b64)
    if result.verified:
        # inject into seller system prompt
        ...
"""
import base64
import email as _email
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Matches the d= tag value inside a DKIM-Signature header.
_DOMAIN_RE = re.compile(r"\bd=([A-Za-z0-9._-]+)", re.IGNORECASE)


@dataclass
class DKIMResult:
    """Result of DKIM verification.

    Attributes
    ----------
    domain : str | None
        The sending domain extracted from the DKIM-Signature ``d=`` tag.
        None if no DKIM-Signature header was found.
    verified : bool
        True only when the cryptographic DKIM signature checked out.
    dns_unavailable : bool
        True when the verification could not be completed because DNS was
        unreachable inside the CVM.  In this case ``domain`` is still
        populated but ``verified`` is False.
    error : str | None
        Human-readable explanation when ``verified`` is False.
    """

    domain: str | None = None
    verified: bool = False
    dns_unavailable: bool = False
    error: str | None = None


async def verify_email_proof(eml_b64: str) -> DKIMResult:
    """Verify the DKIM signature of a base64-encoded .eml file.

    Parameters
    ----------
    eml_b64 : str
        Base64-encoded RFC-2822 email bytes (the raw .eml file content).

    Returns
    -------
    DKIMResult
        See DKIMResult docstring.  The raw email bytes are discarded before
        this function returns.
    """
    # Step 1 — decode
    try:
        eml_bytes: bytes = base64.b64decode(eml_b64)
    except Exception as exc:
        return DKIMResult(error=f"base64 decode failed: {exc}")

    # Step 2 — extract domain from DKIM-Signature header(s)
    try:
        msg = _email.message_from_bytes(eml_bytes)
    except Exception as exc:
        return DKIMResult(error=f"email parse failed: {exc}")

    # There may be multiple DKIM-Signature headers; collect all domains.
    raw_sigs: list[str] = msg.get_all("DKIM-Signature") or []
    if not raw_sigs:
        return DKIMResult(error="No DKIM-Signature header found in the supplied .eml")

    domain: str | None = None
    for sig in raw_sigs:
        m = _DOMAIN_RE.search(sig)
        if m:
            domain = m.group(1).lower().rstrip(".")
            break

    if not domain:
        return DKIMResult(
            error="DKIM-Signature header present but could not extract d= domain tag"
        )

    # Step 3 — cryptographic verification via dkimpy
    try:
        import dkim  # dkimpy — optional dep; graceful fallback if missing

        try:
            verified: bool = bool(dkim.verify(eml_bytes))
        except dkim.ValidationError as exc:
            return DKIMResult(domain=domain, verified=False, error=str(exc))
        except Exception as exc:
            # Catch DNS resolution failures separately so the UI can surface
            # the distinction between "bad signature" and "no DNS in CVM".
            err_str = str(exc).lower()
            if any(kw in err_str for kw in ("dns", "resolve", "timeout", "nxdomain", "nodns")):
                logger.warning("DKIM DNS lookup failed inside TEE: %s", exc)
                return DKIMResult(domain=domain, verified=False, dns_unavailable=True,
                                  error=f"DNS unavailable inside TEE: {exc}")
            return DKIMResult(domain=domain, verified=False, error=str(exc))

        if not verified:
            return DKIMResult(domain=domain, verified=False,
                              error="DKIM signature did not verify (signature mismatch)")

        return DKIMResult(domain=domain, verified=True)

    except ImportError:
        # dkimpy not installed — still return the domain so the UI shows
        # something useful; mark as unverified with a clear reason.
        logger.warning("dkimpy not installed; cannot verify DKIM signature cryptographically")
        return DKIMResult(
            domain=domain,
            verified=False,
            error="dkimpy library not installed — domain extracted but signature not verified",
        )
