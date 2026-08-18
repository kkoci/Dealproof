from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str = ""

    # dstack / TEE
    dstack_simulator_endpoint: str = "http://localhost:8090"
    tee_mode: str = "simulation"  # "simulation" | "production"

    # Blockchain
    rpc_url: str = ""
    private_key: str = ""
    contract_address: str = ""

    # Memory sidecar
    memory_service_url: str = "http://localhost:4011"
    openai_api_key: str = ""

    # Hedera HCS deal outcome publishing (ETHGlobal M7)
    hedera_account_id: str = ""    # HEDERA_ACCOUNT_ID  e.g. "0.0.123456"
    hedera_private_key: str = ""   # HEDERA_PRIVATE_KEY
    hedera_topic_id: str = ""      # HEDERA_TOPIC_ID    e.g. "0.0.789012"
    hedera_network: str = "testnet"  # HEDERA_NETWORK

    # ENS agent identity (ETHGlobal M8)
    ens_rpc_url: str = ""    # Ethereum mainnet RPC for ENS resolution; defaults to cloudflare-eth.com

    # Arc on-chain credential anchoring (ETHGlobal M6)
    arc_rpc_url: str = ""                # ARC_RPC_URL
    arc_chain_id: int = 0                # ARC_CHAIN_ID
    arcid_registry_address: str = ""     # ARCID_REGISTRY_ADDRESS

    # Offer Check Phase 3: billing (per-verification / monthly SaaS pricing)
    stripe_api_key: str = ""       # STRIPE_API_KEY — unset => billing.record_verification_usage() no-ops

    # Offer Check: external market-data comparator (app/offercheck/integrations/market_data.py)
    market_data_api_key: str = ""  # MARKET_DATA_API_KEY — PayScale Compensation API key; unset => fetch_market_range() always returns None

    # Offer Check magic-link auth — gates every Claude-calling offercheck endpoint (see app/offercheck/demo_auth.py)
    offercheck_secret_key: str = ""       # OFFERCHECK_SECRET_KEY — HMAC signing key; app refuses to start without it
    offercheck_api_key: str = ""          # OFFERCHECK_API_KEY — separate Anthropic key for offercheck; falls back to anthropic_api_key if unset
    offercheck_internal_key: str = ""     # OFFERCHECK_INTERNAL_KEY — required to mint demo links via POST /auth/demo-link
    offercheck_demo_base_url: str = "http://localhost:5173"  # base URL used to build shareable demo_url values

    # App
    debug: bool = True
    log_level: str = "INFO"


settings = Settings()
