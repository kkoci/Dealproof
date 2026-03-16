"""
TEE Attestation — dstack/Phala tappd TDX quote generation (Phase 2).

Calls the tappd TdxQuote endpoint to produce an Intel TDX remote attestation
quote. The quote is bound to the negotiation terms via the report_data field:
the SHA-256 hash of the serialised deal terms occupies the first 32 bytes of
the 64-byte report_data, so any verifier can confirm that the quote covers
exactly these terms and no others.

Works identically against the local tappd-simulator and a real Phala CVM.
"""
import json
import hashlib
import httpx
from app.config import settings


async def sign_result(terms: dict) -> str:
    """
    Generate a TDX attestation quote over the negotiation result.

    Steps:
      1. Serialise `terms` to canonical JSON (keys sorted) and SHA-256 hash it.
      2. Pad the 32-byte digest to 64 bytes (TDX report_data size requirement)
         by appending 32 zero bytes.
      3. POST the 64-byte hex string to tappd TdxQuote.
      4. Return the raw hex-encoded TDX quote string from the response.

    Endpoint: POST {DSTACK_SIMULATOR_ENDPOINT}/prpc/Tappd.TdxQuote
    Request:  {"report_data": "<128 hex chars — 64 bytes>"}
    Response: {"quote": "<hex-encoded TDX quote>", "event_log": "..."}

    The returned quote can be verified by any party using Intel's DCAP
    verification stack or Phala's on-chain verifier.
    """
    payload = json.dumps(terms, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).digest()
    # TDX report_data must be exactly 64 bytes; SHA-256 fills the first 32
    report_data = (digest + b"\x00" * 32).hex()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.dstack_simulator_endpoint}/prpc/Tappd.TdxQuote",
            json={"report_data": report_data},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["quote"]
