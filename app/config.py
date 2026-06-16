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

    # App
    debug: bool = True
    log_level: str = "INFO"


settings = Settings()
