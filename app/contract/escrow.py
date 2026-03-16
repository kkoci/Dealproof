"""
Smart contract interaction — Phase 4
Stubs only. Will interact with DealProof.sol on Sepolia via web3.py.
"""
from app.config import settings


async def create_deal_on_chain(deal_id: str, seller_address: str, data_hash: str, value_wei: int) -> str:
    """Phase 4: call DealProof.createDeal() and return tx hash."""
    raise NotImplementedError("On-chain escrow not yet implemented (Phase 4)")


async def complete_deal_on_chain(deal_id: str, tee_attestation: str) -> str:
    """Phase 4: call DealProof.completeDeal() with TEE attestation to release payment."""
    raise NotImplementedError("On-chain deal completion not yet implemented (Phase 4)")


async def refund_deal_on_chain(deal_id: str) -> str:
    """Phase 4: call DealProof.refund() if negotiation fails."""
    raise NotImplementedError("On-chain refund not yet implemented (Phase 4)")
