"""
Smart contract interaction — Phase 4.

Interacts with DealProof.sol on Sepolia via web3.py.

All three public functions are async — they wrap synchronous web3.py calls in
asyncio.to_thread so they don't block the FastAPI event loop.

If CONTRACT_ADDRESS is not configured, EscrowNotConfigured is raised.
Routes catch this and log a warning rather than failing the API call, so the
deal flow works identically with or without an on-chain component.

deal_id (UUID string) → bytes32
  Web3.keccak(text=deal_id) — deterministic, collision-resistant, 32 bytes.

data_hash (64-char hex string) → bytes32
  bytes.fromhex(data_hash) — direct conversion, exactly 32 bytes.

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
            {"name": "seller", "type": "address"},
            {"name": "dataHash", "type": "bytes32"},
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
    """Raised when CONTRACT_ADDRESS is not set in settings."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deal_id_to_bytes32(deal_id: str) -> bytes:
    """Convert a UUID string to a deterministic 32-byte value via keccak256."""
    return Web3.keccak(text=deal_id)


def _data_hash_to_bytes32(data_hash: str) -> bytes:
    """Convert a 64-char hex SHA-256 string to 32 bytes."""
    return bytes.fromhex(data_hash)


def _get_web3_and_contract():
    """Return a configured (Web3, Contract) pair. Does not require async."""
    if not settings.contract_address:
        raise EscrowNotConfigured(
            "CONTRACT_ADDRESS is not set — on-chain escrow is disabled"
        )
    w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.contract_address),
        abi=_ABI,
    )
    return w3, contract


def _send_transaction(contract_fn, value_wei: int = 0) -> str:
    """
    Build, sign, and broadcast a transaction synchronously.

    Called via asyncio.to_thread from the async wrappers below.
    Returns the transaction hash as a hex string.
    """
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


async def create_deal_on_chain(
    deal_id: str,
    seller_address: str,
    data_hash: str,
    value_wei: int,
) -> str:
    """
    Call DealProof.createDeal() and deposit escrow funds.

    Parameters
    ----------
    deal_id       : UUID string from the API (converted to bytes32 via keccak256)
    seller_address: Checksummed Ethereum address of the seller
    data_hash     : 64-char hex SHA-256 of the dataset
    value_wei     : ETH amount in wei to deposit as escrow

    Returns
    -------
    Transaction hash as a hex string.
    """
    w3, contract = _get_web3_and_contract()
    deal_id_b32 = _deal_id_to_bytes32(deal_id)
    data_hash_b32 = _data_hash_to_bytes32(data_hash)
    seller = Web3.to_checksum_address(seller_address)
    negotiation_window = 3600  # 1 hour — buyer cannot refund before this expires

    contract_fn = contract.functions.createDeal(
        deal_id_b32,
        seller,
        data_hash_b32,
        negotiation_window,
    )
    return await asyncio.to_thread(_send_transaction, contract_fn, value_wei)


async def complete_deal_on_chain(deal_id: str, tee_attestation: str) -> str:
    """
    Call DealProof.completeDeal() — commits attestation hash and releases escrow.

    The TEE attestation string is UTF-8 encoded to bytes; keccak256 of this is
    stored on-chain in attestationHashes[dealId] for independent verification.

    Parameters
    ----------
    deal_id        : UUID string (converted to bytes32 via keccak256)
    tee_attestation: Attestation string from sign_result() — sim_quote or real TDX

    Returns
    -------
    Transaction hash as a hex string.
    """
    _, contract = _get_web3_and_contract()
    deal_id_b32 = _deal_id_to_bytes32(deal_id)
    attestation_bytes = tee_attestation.encode("utf-8")

    contract_fn = contract.functions.completeDeal(deal_id_b32, attestation_bytes)
    return await asyncio.to_thread(_send_transaction, contract_fn)


async def refund_deal_on_chain(deal_id: str) -> str:
    """
    Call DealProof.refund() — returns escrowed ETH to the buyer.

    This will revert on-chain if called before the negotiation window expires.
    Do not call this immediately after a failed negotiation — wait for the
    deadline (set to 1 hour after deal creation by default).

    Parameters
    ----------
    deal_id: UUID string (converted to bytes32 via keccak256)

    Returns
    -------
    Transaction hash as a hex string.
    """
    _, contract = _get_web3_and_contract()
    deal_id_b32 = _deal_id_to_bytes32(deal_id)

    contract_fn = contract.functions.refund(deal_id_b32)
    return await asyncio.to_thread(_send_transaction, contract_fn)
