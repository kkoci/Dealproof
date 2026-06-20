"""
Session-level mocks for dependencies not installed in this dev environment.

web3 is only needed for the on-chain escrow Phase 4 feature. All other
tests run against mocked attestation (sign_result) and a tmp SQLite DB.
Adding sys.modules stubs here lets the FastAPI TestClient import app.main
without requiring the web3 package to be installed.
"""
import sys
from unittest.mock import MagicMock


def _stub_blockchain():
    """
    Install minimal stubs for blockchain packages not installed in this dev
    environment (web3, eth_account).  These are only needed for on-chain
    escrow/Arc-anchor features — all other code paths are mocked at test level.
    """
    for pkg in (
        "web3",
        "web3.middleware",
        "web3.exceptions",
        "eth_account",
        "eth_account.messages",
    ):
        if pkg not in sys.modules:
            sys.modules[pkg] = MagicMock()

    # Give eth_account.Account and web3.Web3 the attribute shape the modules expect
    sys.modules["web3"].Web3 = MagicMock()
    sys.modules["web3"].Web3.HTTPProvider = MagicMock()
    sys.modules["eth_account"].Account = MagicMock()
    sys.modules["eth_account.messages"].encode_defunct = MagicMock()


_stub_blockchain()
