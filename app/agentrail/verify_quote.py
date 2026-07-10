"""
DCAP quote verification — Phase 1.

Reuses the TDX TD Report Body parsing DealProof core already relies on
(app/tee/attestation.py get_enclave_quote) so the agent-rail demo can prove
its attestation quote is well-formed without re-deriving the layout.
"""
from app.config import settings


def verify_quote(quote: str) -> dict:
    """
    Structural verification of a DealProof attestation quote.

    Simulation mode: quote is "sim_quote:<sha256 hex>" — verified by format only.
    Production mode: quote is a hex-encoded TDX quote — verified by length, with
    MRTD extracted from the TD Report Body (offset 64, 48 bytes), matching
    app.tee.attestation.get_enclave_quote's parsing.

    Returns {"valid": bool, "mode": str, "mrenclave": str | None, "byte_length": int}.
    """
    if settings.tee_mode == "simulation" or quote.startswith("sim_quote:"):
        digest = quote.removeprefix("sim_quote:")
        is_hex = len(digest) > 0 and all(c in "0123456789abcdef" for c in digest.lower())
        return {
            "valid": is_hex,
            "mode": "simulation",
            "mrenclave": None,
            "byte_length": len(digest) // 2,
        }

    try:
        quote_bytes = bytes.fromhex(quote)
    except ValueError:
        return {"valid": False, "mode": "production", "mrenclave": None, "byte_length": 0}

    mrenclave = quote_bytes[64:112].hex() if len(quote_bytes) >= 112 else None
    return {
        "valid": len(quote_bytes) >= 112,
        "mode": "production",
        "mrenclave": mrenclave,
        "byte_length": len(quote_bytes),
    }
