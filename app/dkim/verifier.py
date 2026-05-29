"""
DKIM email proof verifier — Phase 6.

Design
------
The seller submits a base64-encoded .eml file as `seller_email_eml` in the
DealCreate payload.  This module runs entirely inside the TEE and:

  1. Decodes the base64 payload to raw RFC-2822 email bytes.
  2. Extracts the `d=` tag from every DKIM-Signature header to identify the
     sending domain (e.g. "company.com").
  3. Calls dkimpy's verify() using a custom DNS resolver that queries
     Cloudflare's DNS-over-HTTPS endpoint (https://1.1.1.1/dns-query) so
     DKIM public keys can be fetched inside the Phala TDX CVM where UDP
     port 53 is blocked.
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
from dataclasses import dataclass

import httpx

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
        Retained for API compatibility; always False now that DNS lookups use
        DoH and are not blocked inside the CVM.
    error : str | None
        Human-readable explanation when ``verified`` is False.
    """

    domain: str | None = None
    verified: bool = False
    dns_unavailable: bool = False
    error: str | None = None


class _TXTRecord:
    """Wraps DoH TXT data to match the interface dkimpy expects from dnsfunc."""

    __slots__ = ("strings",)

    def __init__(self, strings: list[bytes]) -> None:
        self.strings = strings


def _doh_get_txt(
    name: "bytes | str",
    rdatatype: str = "TXT",
    timeout: int = 5,
    **_kwargs,
) -> "list[_TXTRecord]":
    """Fetch DNS TXT records via Cloudflare DoH (https://1.1.1.1/dns-query).

    Injected as dkimpy's dnsfunc so DKIM key lookups work inside the Phala
    TDX CVM where UDP port 53 is blocked.  HTTPS port 443 is allowed.
    """
    host = name.decode("ascii") if isinstance(name, bytes) else name
    try:
        resp = httpx.get(
            "https://1.1.1.1/dns-query",
            params={"name": host, "type": "TXT"},
            headers={"Accept": "application/dns-json"},
            timeout=float(timeout),
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise OSError(f"DoH lookup failed for {host}: {exc}") from exc

    records: list[_TXTRecord] = []
    for answer in data.get("Answer", []):
        if answer.get("type") != 16:  # 16 = TXT
            continue
        raw: str = answer.get("data", "")
        # DoH JSON wraps each TXT string segment in double-quotes.
        parts = [p.encode() for p in re.findall(r'"([^"]*)"', raw)]
        if not parts:
            # No quoted segments found — treat the whole value as one string.
            parts = [raw.encode()]
        records.append(_TXTRecord(parts))
    return records


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

    # Step 3 — cryptographic verification via dkimpy with DoH-based DNS
    try:
        import dkim  # dkimpy — optional dep; graceful fallback if missing

        try:
            d = dkim.DKIM(eml_bytes)
            d.dnsfunc = _doh_get_txt
            verified: bool = bool(d.verify())
        except dkim.ValidationError as exc:
            return DKIMResult(domain=domain, verified=False, error=str(exc))
        except Exception as exc:
            return DKIMResult(domain=domain, verified=False, error=str(exc))

        if not verified:
            return DKIMResult(
                domain=domain,
                verified=False,
                error="DKIM signature did not verify (signature mismatch)",
            )

        return DKIMResult(domain=domain, verified=True)

    except ImportError:
        logger.warning("dkimpy not installed; cannot verify DKIM signature cryptographically")
        return DKIMResult(
            domain=domain,
            verified=False,
            error="dkimpy library not installed — domain extracted but signature not verified",
        )
