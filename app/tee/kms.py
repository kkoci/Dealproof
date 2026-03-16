"""
Key Management Service — dstack/Phala tappd integration (Phase 2).

Calls the tappd DeriveKey endpoint to retrieve a hardware-bound key whose
derivation is tied to the CVM's TDX measurement registers. The same call
works against both the local tappd-simulator (docker-compose dev mode) and
a real Phala Cloud CVM (production mode) — the only difference is which
host DSTACK_SIMULATOR_ENDPOINT points at.
"""
import httpx
from app.config import settings


async def get_signing_key() -> bytes:
    """
    Derive a hardware-bound signing key from the dstack tappd KMS.

    Endpoint: POST {DSTACK_SIMULATOR_ENDPOINT}/prpc/Tappd.DeriveKey
    Request:  {"path": "dealproof/signing-key", "subject": "dealproof-v1"}
    Response: {"key": "<hex-encoded key>", "certificate_chain": [...]}

    The returned key is unique to this CVM's hardware identity and cannot
    be reproduced outside the enclave, giving the deal a hardware root of
    trust even before the TDX quote is generated.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.dstack_simulator_endpoint}/prpc/Tappd.DeriveKey",
            json={"path": "dealproof/signing-key", "subject": "dealproof-v1"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        raw_key = data["key"]
        # Strip optional 0x prefix before decoding
        return bytes.fromhex(raw_key.removeprefix("0x"))
