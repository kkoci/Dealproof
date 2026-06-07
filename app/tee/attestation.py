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


async def get_enclave_quote() -> dict:
    """
    Fetch a raw TDX quote with zero report_data (not bound to any deal terms).

    Used by GET /api/attest so a client can verify the enclave before sending
    any sensitive payload.  The MRTD (TD measurement register) is extracted from
    the TD Report Body at offset 16 (after ATTRIBUTES+XFAM, 48-byte SHA-384).

    Returns {"quote": hex_str, "mrenclave": hex_str | None}
    """
    zero_report_data = "00" * 64  # 64 zero bytes, hex-encoded

    if settings.tee_mode == "simulation":
        sim_hash = hashlib.sha256(b"simulation_enclave").hexdigest()
        return {
            "quote": "sim_quote:" + hashlib.sha256(zero_report_data.encode()).hexdigest(),
            "mrenclave": "sim_mrenclave:" + sim_hash,
        }

    transport = httpx.AsyncHTTPTransport(uds="/var/run/tappd.sock")
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/prpc/Tappd.TdxQuote",
            json={"report_data": zero_report_data},
            timeout=10.0,
        )
        response.raise_for_status()
        quote_hex = response.json()["quote"]

    # Extract MRTD from TD Report Body (TDX TD10 layout):
    #   Quote header: 48 bytes
    #   TD Report Body: ATTRIBUTES(8) + XFAM(8) + MRTD(48) + ...
    #   → MRTD absolute offset: 48 + 16 = 64, length 48 bytes
    mrenclave: str | None = None
    try:
        qb = bytes.fromhex(quote_hex)
        if len(qb) >= 112:
            mrenclave = qb[64:112].hex()
    except (ValueError, IndexError):
        pass

    return {"quote": quote_hex, "mrenclave": mrenclave}


async def sign_result(terms: dict, memory_hash: str = "") -> str:
    """
    Generate a TDX attestation quote over the negotiation result.

    Steps:
      1. Serialise `terms` to canonical JSON (keys sorted) and SHA-256 hash it.
         When memory_hash is non-empty, it is included in the payload so the
         quote also covers the agents' memory state at settlement time.
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
    attested_payload = dict(terms)
    if memory_hash:
        attested_payload["memory_hash"] = memory_hash
        attested_payload["memory_attested"] = True
    payload = json.dumps(attested_payload, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).digest()
    # TDX report_data must be exactly 64 bytes; SHA-256 fills the first 32
    report_data = (digest + b"\x00" * 32).hex()

    if settings.tee_mode == "simulation":
        # No real TEE available — return a deterministic local mock quote.
        return "sim_quote:" + hashlib.sha256(report_data.encode()).hexdigest()

    # Production: tappd is available via Unix domain socket on Phala Cloud CVM
    transport = httpx.AsyncHTTPTransport(uds="/var/run/tappd.sock")
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/prpc/Tappd.TdxQuote",
            json={"report_data": report_data},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["quote"]
