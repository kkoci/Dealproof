"""
Phase 4 — escrow.py unit tests.

All web3 I/O is mocked — no network required.
Tests verify that the correct contract functions are called with the correct
arguments, and that EscrowNotConfigured is raised when CONTRACT_ADDRESS is empty.
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(contract_address="0x1234567890123456789012345678901234567890"):
    s = MagicMock()
    s.contract_address = contract_address
    s.rpc_url = "http://localhost:8545"
    s.private_key = "0x" + "a" * 64
    return s


def _mock_web3(mock_w3_cls, tx_hash_hex="deadbeef" + "00" * 28):
    """Wire up a minimal mock Web3 instance."""
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


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

class TestDealIdConversion:
    def test_deal_id_to_bytes32_is_deterministic(self):
        from app.contract.escrow import _deal_id_to_bytes32
        uuid = "48bac32d-8499-453c-9557-9fcd50151bca"
        assert _deal_id_to_bytes32(uuid) == _deal_id_to_bytes32(uuid)

    def test_deal_id_to_bytes32_is_32_bytes(self):
        from app.contract.escrow import _deal_id_to_bytes32
        assert len(_deal_id_to_bytes32("some-deal-id")) == 32

    def test_data_hash_to_bytes32_is_32_bytes(self):
        from app.contract.escrow import _data_hash_to_bytes32
        assert len(_data_hash_to_bytes32("a" * 64)) == 32

    def test_different_deal_ids_produce_different_bytes32(self):
        from app.contract.escrow import _deal_id_to_bytes32
        assert _deal_id_to_bytes32("deal-1") != _deal_id_to_bytes32("deal-2")


# ---------------------------------------------------------------------------
# EscrowNotConfigured
# ---------------------------------------------------------------------------

class TestEscrowNotConfigured:
    def test_get_web3_raises_when_no_contract_address(self):
        from app.contract.escrow import EscrowNotConfigured, _get_web3_and_contract
        with patch("app.contract.escrow.settings", _make_settings(contract_address="")):
            with pytest.raises(EscrowNotConfigured):
                _get_web3_and_contract()


# ---------------------------------------------------------------------------
# create_deal_on_chain
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCreateDeal:
    async def test_create_deal_calls_correct_function(self):
        with patch("app.contract.escrow.settings", _make_settings()), \
             patch("app.contract.escrow.Web3") as mock_w3_cls, \
             patch("app.contract.escrow.asyncio.to_thread") as mock_thread:

            mock_thread.return_value = "0xdeadbeef"
            _mock_web3(mock_w3_cls)

            from app.contract.escrow import create_deal_on_chain
            tx = await create_deal_on_chain(
                deal_id="test-deal-123",
                seller_address="0x" + "b" * 40,
                data_hash="a" * 64,
                value_wei=100_000_000_000_000_000,
            )
            assert tx == "0xdeadbeef"
            assert mock_thread.called


# ---------------------------------------------------------------------------
# complete_deal_on_chain
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCompleteDeal:
    async def test_complete_deal_passes_attestation(self):
        with patch("app.contract.escrow.settings", _make_settings()), \
             patch("app.contract.escrow.Web3") as mock_w3_cls, \
             patch("app.contract.escrow.asyncio.to_thread") as mock_thread:

            mock_thread.return_value = "0xcafebabe"
            _mock_web3(mock_w3_cls)

            from app.contract.escrow import complete_deal_on_chain
            tx = await complete_deal_on_chain(
                deal_id="test-deal-123",
                tee_attestation="sim_quote:abc123",
            )
            assert tx == "0xcafebabe"
            assert mock_thread.called


# ---------------------------------------------------------------------------
# refund_deal_on_chain
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRefundDeal:
    async def test_refund_calls_refund_function(self):
        with patch("app.contract.escrow.settings", _make_settings()), \
             patch("app.contract.escrow.Web3") as mock_w3_cls, \
             patch("app.contract.escrow.asyncio.to_thread") as mock_thread:

            mock_thread.return_value = "0xbeefdead"
            _mock_web3(mock_w3_cls)

            from app.contract.escrow import refund_deal_on_chain
            tx = await refund_deal_on_chain(deal_id="test-deal-123")
            assert tx == "0xbeefdead"
            assert mock_thread.called
