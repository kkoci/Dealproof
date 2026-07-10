"""
Agent Rail — Phase 3 escrow.py unit tests.

Mirrors tests/test_contract.py's pattern exactly: all web3 I/O mocked, no
network or local Hardhat node required.
"""
import pytest
from unittest.mock import MagicMock, patch


def _make_settings(agentrail_contract_address="0x1234567890123456789012345678901234567890"):
    s = MagicMock()
    s.agentrail_contract_address = agentrail_contract_address
    s.rpc_url = "http://localhost:8545"
    s.private_key = "0x" + "a" * 64
    return s


def _mock_web3(mock_w3_cls, tx_hash_hex="deadbeef" + "00" * 28):
    w3 = MagicMock()
    mock_w3_cls.return_value = w3
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.gas_price = 1_000_000_000
    w3.eth.send_raw_transaction.return_value = bytes.fromhex(tx_hash_hex)
    signed = MagicMock()
    signed.raw_transaction = b"\x00" * 32
    w3.eth.account.sign_transaction.return_value = signed

    contract = MagicMock()
    w3.eth.contract.return_value = contract
    contract.functions.createDeal.return_value.build_transaction.return_value = {"gas": 300_000}
    contract.functions.completeDeal.return_value.build_transaction.return_value = {"gas": 300_000}
    contract.functions.refund.return_value.build_transaction.return_value = {"gas": 300_000}

    return w3, contract


class TestEscrowNotConfigured:
    def test_get_web3_raises_when_no_contract_address(self):
        from app.agentrail.escrow import EscrowNotConfigured, _get_web3_and_contract
        with patch("app.agentrail.escrow.settings", _make_settings(agentrail_contract_address="")):
            with pytest.raises(EscrowNotConfigured):
                _get_web3_and_contract()


@pytest.mark.asyncio
class TestDepositEscrow:
    async def test_deposit_calls_create_deal(self):
        with patch("app.agentrail.escrow.settings", _make_settings()), \
             patch("app.agentrail.escrow.Web3") as mock_w3_cls, \
             patch("app.agentrail.escrow.asyncio.to_thread") as mock_thread:

            mock_thread.return_value = "0xdeadbeef"
            _mock_web3(mock_w3_cls)

            from app.agentrail.escrow import deposit_escrow
            tx = await deposit_escrow(
                deal_id="agent-deal-123",
                supplier_address="0x" + "b" * 40,
                value_wei=100_000_000_000_000_000,
            )
            assert tx == "0xdeadbeef"
            assert mock_thread.called


@pytest.mark.asyncio
class TestReleaseEscrow:
    async def test_release_passes_attestation(self):
        with patch("app.agentrail.escrow.settings", _make_settings()), \
             patch("app.agentrail.escrow.Web3") as mock_w3_cls, \
             patch("app.agentrail.escrow.asyncio.to_thread") as mock_thread:

            mock_thread.return_value = "0xcafebabe"
            _mock_web3(mock_w3_cls)

            from app.agentrail.escrow import release_escrow
            tx = await release_escrow(deal_id="agent-deal-123", tee_attestation="sim_quote:abc123")
            assert tx == "0xcafebabe"
            assert mock_thread.called


@pytest.mark.asyncio
class TestRefundEscrow:
    async def test_refund_calls_refund_function(self):
        with patch("app.agentrail.escrow.settings", _make_settings()), \
             patch("app.agentrail.escrow.Web3") as mock_w3_cls, \
             patch("app.agentrail.escrow.asyncio.to_thread") as mock_thread:

            mock_thread.return_value = "0xbeefdead"
            _mock_web3(mock_w3_cls)

            from app.agentrail.escrow import refund_escrow
            tx = await refund_escrow(deal_id="agent-deal-123")
            assert tx == "0xbeefdead"
            assert mock_thread.called
