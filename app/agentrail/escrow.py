"""
Smart contract interaction — Agent Rail Phase 3.

Mirrors app/contract/escrow.py's structure exactly, against AgentDealEscrow.sol
(contracts/src/AgentDealEscrow.sol) instead of DealProof.sol. Not deployed to
any live network as of Phase 3 (see AGENTRAIL_CONTRACT_ADDRESS in app/config.py) —
these functions are fully unit-tested against a mocked web3.py (see
tests/test_agentrail_escrow.py), same as core's escrow tests. No local Hardhat
node or Sepolia RPC is required to run the test suite.

If AGENTRAIL_CONTRACT_ADDRESS is not configured, EscrowNotConfigured is raised.
routes.py catches this and logs a warning rather than failing the API call,
matching DealProof core's resilience pattern for Step 1b/3b.

deal_id (UUID string) → bytes32
  Web3.keccak(text=deal_id) — deterministic, collision-resistant, 32 bytes.

tee_attestation (str) → bytes
  UTF-8 encoded. keccak256 of this is stored on-chain in attestationHashes.
"""
import asyncio
import logging

from web3 import Web3

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contract ABI — only the functions we call from Python
# ---------------------------------------------------------------------------

_ABI = [
    {
        "inputs": [
            {"name": "dealId", "type": "bytes32"},
            {"name": "supplier", "type": "address"},
            {"name": "negotiationWindow", "type": "uint256"},
        ],
        "name": "createDeal",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "dealId", "type": "bytes32"},
            {"name": "teeAttestation", "type": "bytes"},
        ],
        "name": "completeDeal",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "dealId", "type": "bytes32"},
        ],
        "name": "refund",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "dealId", "type": "bytes32"},
        ],
        "name": "getAttestationHash",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EscrowNotConfigured(Exception):
    """Raised when AGENTRAIL_CONTRACT_ADDRESS is not set in settings."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deal_id_to_bytes32(deal_id: str) -> bytes:
    """Convert a UUID string to a deterministic 32-byte value via keccak256."""
    return Web3.keccak(text=deal_id)


def _get_web3_and_contract():
    """Return a configured (Web3, Contract) pair. Does not require async."""
    if not settings.agentrail_contract_address:
        raise EscrowNotConfigured(
            "AGENTRAIL_CONTRACT_ADDRESS is not set — Agent Rail on-chain escrow is disabled"
        )
    w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.agentrail_contract_address),
        abi=_ABI,
    )
    return w3, contract


def _send_transaction(contract_fn, value_wei: int = 0) -> str:
    """Build, sign, and broadcast a transaction synchronously. Called via
    asyncio.to_thread from the async wrappers below."""
    w3, _ = _get_web3_and_contract()
    from eth_account import Account

    account = Account.from_key(settings.private_key)
    nonce = w3.eth.get_transaction_count(account.address)

    tx = contract_fn.build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
            "gas": 300_000,
            "gasPrice": w3.eth.gas_price,
            "value": value_wei,
        }
    )
    signed = w3.eth.account.sign_transaction(tx, settings.private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logger.info(f"Transaction sent: {tx_hash.hex()}")
    return tx_hash.hex()


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def deposit_escrow(deal_id: str, supplier_address: str, value_wei: int) -> str:
    """Call AgentDealEscrow.createDeal() and deposit escrow funds."""
    w3, contract = _get_web3_and_contract()
    deal_id_b32 = _deal_id_to_bytes32(deal_id)
    supplier = Web3.to_checksum_address(supplier_address)
    negotiation_window = 3600  # 1 hour — buyer cannot refund before this expires

    contract_fn = contract.functions.createDeal(deal_id_b32, supplier, negotiation_window)
    return await asyncio.to_thread(_send_transaction, contract_fn, value_wei)


async def release_escrow(deal_id: str, tee_attestation: str) -> str:
    """Call AgentDealEscrow.completeDeal() — commits attestation hash and
    releases escrow to the supplier."""
    _, contract = _get_web3_and_contract()
    deal_id_b32 = _deal_id_to_bytes32(deal_id)
    attestation_bytes = tee_attestation.encode("utf-8")

    contract_fn = contract.functions.completeDeal(deal_id_b32, attestation_bytes)
    return await asyncio.to_thread(_send_transaction, contract_fn)


async def refund_escrow(deal_id: str) -> str:
    """Call AgentDealEscrow.refund() — returns escrowed ETH to the buyer.
    Reverts on-chain if called before the negotiation window expires."""
    _, contract = _get_web3_and_contract()
    deal_id_b32 = _deal_id_to_bytes32(deal_id)

    contract_fn = contract.functions.refund(deal_id_b32)
    return await asyncio.to_thread(_send_transaction, contract_fn)
