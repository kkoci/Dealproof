"""
Arc on-chain credential anchoring — ETHGlobal M6.

Calls ArcIDRegistry.register() on Arc with the deal's TDX attestation quote,
anchoring the credential hash on-chain via the ArcID agent identity mechanism.

Pattern mirrors app/contract/escrow.py exactly:
- Synchronous web3 call wrapped in asyncio.to_thread
- ArcNotConfigured raised when env vars absent — non-fatal to credential endpoint
- Simulation-mode quotes (sim_quote:...) raise ArcNotConfigured — Arc requires real TDX

The agentId returned by register() is keccak256(mrtd, reportData, attestedSigner)
and becomes the arc_record_id stored in the deal's arc_anchors row.

Reference: ../arcid/arcid/backend/registry/register.py (ArcID hackathon project)
"""
import asyncio
import logging

from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ABI — only the functions and events we use
# ---------------------------------------------------------------------------

_ABI = [
    {
        "inputs": [
            {"name": "dcapQuote",     "type": "bytes"},
            {"name": "reportDataSig", "type": "bytes"},
            {"name": "name",          "type": "string"},
        ],
        "name": "register",
        "outputs": [{"name": "agentId", "type": "bytes32"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "agentId",        "type": "bytes32"},
            {"indexed": True,  "name": "attestedSigner",  "type": "address"},
            {"indexed": False, "name": "mrtd",            "type": "bytes32"},
            {"indexed": False, "name": "name",            "type": "string"},
            {"indexed": False, "name": "gasSponsored",    "type": "bool"},
            {"indexed": False, "name": "registeredAt",    "type": "uint64"},
        ],
        "name": "AgentRegistered",
        "type": "event",
    },
]

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class ArcNotConfigured(Exception):
    """Raised when Arc env vars are absent or the attestation is a simulation quote."""


# ---------------------------------------------------------------------------
# Internal sync implementation (called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _anchor_sync(deal_id: str, credential_hash: str, attestation_hex: str) -> dict:
    if not settings.arcid_registry_address:
        raise ArcNotConfigured("ARCID_REGISTRY_ADDRESS not configured")
    if not settings.arc_rpc_url:
        raise ArcNotConfigured("ARC_RPC_URL not configured")
    if not settings.private_key:
        raise ArcNotConfigured("PRIVATE_KEY not configured")
    if attestation_hex.startswith("sim_quote:"):
        raise ArcNotConfigured("Simulation quote — Arc anchoring requires real TDX attestation")

    w3 = Web3(Web3.HTTPProvider(settings.arc_rpc_url))
    if not w3.is_connected():
        raise RuntimeError(f"Cannot reach Arc RPC at {settings.arc_rpc_url}")

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.arcid_registry_address),
        abi=_ABI,
    )
    operator = Account.from_key(settings.private_key)

    # The TDX report_data field is SHA-256(sign_payload) || 32 zero bytes.
    # credential_hash == SHA-256(credential sign_payload) == report_data[0:32].
    # We sign this 64-byte field so DCAPVerifier can recover attestedSigner.
    report_data_bytes = bytes.fromhex(credential_hash) + b"\x00" * 32
    msg = encode_defunct(primitive=report_data_bytes)
    signed_msg = w3.eth.account.sign_message(msg, settings.private_key)
    report_data_sig = signed_msg.signature

    # Build the raw DCAP quote bytes from the hex attestation string
    quote_hex = attestation_hex.lstrip("0x")
    dcap_quote_bytes = bytes.fromhex(quote_hex)

    name = f"DealProof-Credential:{deal_id[:8]}"

    nonce = w3.eth.get_transaction_count(operator.address)
    tx = contract.functions.register(
        dcap_quote_bytes,
        report_data_sig,
        name,
    ).build_transaction({
        "from": operator.address,
        "nonce": nonce,
        "gas": 2_500_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": settings.arc_chain_id,
    })
    signed_tx = w3.eth.account.sign_transaction(tx, settings.private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status != 1:
        raise RuntimeError(f"register() reverted in tx {tx_hash.hex()}")

    # Decode the AgentRegistered event for the canonical agentId
    events = contract.events.AgentRegistered().process_receipt(receipt)
    if events:
        arc_record_id = "0x" + events[0]["args"]["agentId"].hex()
    else:
        # Idempotent re-register — compute agentId offline (not available without mrtd)
        arc_record_id = tx_hash.hex()

    logger.info(f"Arc anchor: tx={tx_hash.hex()}, record_id={arc_record_id}")
    return {"tx_hash": tx_hash.hex(), "arc_record_id": arc_record_id}


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def anchor_credential_on_arc(
    deal_id: str,
    credential_hash: str,
    attestation_hex: str,
) -> dict:
    """
    Anchor a TeamDynamicsCredential on Arc via ArcIDRegistry.register().

    Parameters
    ----------
    deal_id         : UUID string of the deal
    credential_hash : SHA-256 hex of the credential sign_payload
    attestation_hex : Raw TDX DCAP quote hex from sign_result()

    Returns
    -------
    { tx_hash, arc_record_id }

    Raises ArcNotConfigured when env vars are missing or attestation is a sim quote.
    """
    return await asyncio.to_thread(_anchor_sync, deal_id, credential_hash, attestation_hex)
