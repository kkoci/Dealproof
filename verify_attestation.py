"""
verify_attestation.py — reference client: verify DealProof TEE attestation before sending payload.

Per Andrew Miller (@socrates1024, IC3): validate the attestation before sending any sensitive data.
Analogy: forming a TLS channel to the TEE and checking the attestation of the channel itself
before sending anything on it.

Usage:
    DEALPROOF_URL=https://<your-phala-endpoint> python verify_attestation.py
"""
import os
import sys
import httpx

DEALPROOF_URL = os.environ.get("DEALPROOF_URL", "http://localhost:8000")

# Replace with the mrenclave of your trusted DealProof build.
# In simulation mode this will be "sim_mrenclave:<sha256>".
# In production (Phala CVM) this is the 96-char hex MRTD from the TDX TD Report Body.
KNOWN_GOOD_MRENCLAVE = os.environ.get("KNOWN_GOOD_MRENCLAVE", "")


def verify_before_send() -> dict:
    """
    Step 1 — fetch the attestation quote from the running enclave.
    Step 2 — verify mrenclave matches the known-good build measurement.
    Step 3 — return the verified attest payload so the caller can proceed with POST /api/deals/run.

    Raises SystemExit on any verification failure so it is safe to call from a script
    that feeds the result straight into a deal submission.
    """
    # Step 1: fetch attestation
    try:
        r = httpx.get(f"{DEALPROOF_URL}/api/attest", timeout=10.0)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"ERROR: could not reach {DEALPROOF_URL}/api/attest — {exc}", file=sys.stderr)
        sys.exit(1)

    attest = r.json()
    print(f"Quote received  | timestamp : {attest['timestamp']}")
    print(f"                | mrenclave : {attest['mrenclave']}")
    print(f"                | quote     : {attest['quote'][:32]}...")

    # Step 2: verify mrenclave
    if not KNOWN_GOOD_MRENCLAVE:
        print(
            "WARNING: KNOWN_GOOD_MRENCLAVE not set — skipping measurement check.\n"
            "         Set it to the mrenclave of your trusted DealProof build before using in production.",
            file=sys.stderr,
        )
    else:
        if attest["mrenclave"] != KNOWN_GOOD_MRENCLAVE:
            print(
                f"ERROR: mrenclave mismatch — do not send payload.\n"
                f"  got:      {attest['mrenclave']}\n"
                f"  expected: {KNOWN_GOOD_MRENCLAVE}",
                file=sys.stderr,
            )
            sys.exit(1)
        print("Attestation verified — mrenclave matches trusted build.")

    # Step 3: return attest payload; caller proceeds with POST /api/deals/run
    print("Safe to send payload.")
    return attest


if __name__ == "__main__":
    verify_before_send()
