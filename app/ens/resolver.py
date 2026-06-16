"""
ENS reverse resolution for DealProof agent identities.

Resolves Ethereum wallet addresses to ENS names (e.g. 0xabc... → "alice.eth").
Used to give deal participants human-readable on-chain identities.

Falls back gracefully — no ENS name is not an error, just an unnamed agent.
Uses web3.py ENS support (already installed for escrow.py).
Default RPC: https://cloudflare-eth.com — free public mainnet, no API key needed.
"""
import asyncio
import logging

from web3 import Web3

from app.config import settings

logger = logging.getLogger(__name__)

_w3: Web3 | None = None


def _get_web3() -> Web3 | None:
    global _w3
    if _w3 is None:
        rpc = settings.ens_rpc_url or "https://cloudflare-eth.com"
        try:
            _w3 = Web3(Web3.HTTPProvider(rpc))
        except Exception as exc:
            logger.warning(f"ENS: failed to initialise Web3 — {exc}")
            return None
    return _w3


def _reverse_resolve(address: str) -> str | None:
    w3 = _get_web3()
    if w3 is None:
        return None
    try:
        name = w3.ens.name(address)
        return name  # None when no reverse record is set
    except Exception as exc:
        logger.warning(f"ENS: reverse resolution failed for {address} — {exc}")
        return None


def _forward_resolve(name: str) -> str | None:
    w3 = _get_web3()
    if w3 is None:
        return None
    try:
        return w3.ens.address(name)
    except Exception as exc:
        logger.warning(f"ENS: forward resolution failed for {name} — {exc}")
        return None


async def resolve_ens_name(address: str) -> str | None:
    """Reverse-resolve an Ethereum address to its ENS name, or None if not set."""
    return await asyncio.to_thread(_reverse_resolve, address)


async def resolve_ens_address(name: str) -> str | None:
    """Forward-resolve an ENS name to its checksummed address, or None if not set."""
    return await asyncio.to_thread(_forward_resolve, name)
