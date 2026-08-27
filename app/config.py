from pydantic import AliasChoices, Field
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
    # STRIPE_API_KEY (this repo's original name) or STRIPE_SECRET_KEY (Stripe's own
    # conventional name, e.g. what `stripe listen`/most Stripe docs and integrations
    # call it) -- accepting both means a real .env set up the standard Stripe way
    # doesn't silently fail to load. Found live: a real STRIPE_SECRET_KEY in .env was
    # never being picked up because this field only matched STRIPE_API_KEY exactly.
    # Unset => billing.record_verification_usage() no-ops.
    stripe_api_key: str = Field(default="", validation_alias=AliasChoices("STRIPE_API_KEY", "STRIPE_SECRET_KEY"))
    stripe_webhook_secret: str = ""  # STRIPE_WEBHOOK_SECRET — signs the account-wide Checkout webhook (Phase 4 credits); unset => the webhook route rejects everything (never a silent-accept fallback)
    # Phase 4 payment gating (app/offercheck/credits.py) — same "off by default, explicit opt-in"
    # convention as every other paid/external integration in this vertical (StripeNotConfigured,
    # ArcNotConfigured, AtsNotConfigured, the memory sidecar): False means _maybe_attest()
    # produces the proof bundle exactly as it always has, with zero credit/company involvement —
    # this is deliberate, not a placeholder, since flipping the default would silently require
    # every existing company (and this entire test suite) to already hold a credit balance.
    offercheck_payment_gating_enabled: bool = False  # OFFERCHECK_PAYMENT_GATING_ENABLED

    # Offer Check: external market-data comparator (app/offercheck/integrations/market_data.py)
    # BLS OEWS (US): optional registration key for higher API rate limits — unauthenticated
    # requests work too, just at a lower quota. ONS ASHE (UK) needs no key at all.
    bls_api_key: str = ""  # BLS_API_KEY — optional; unset => fetch_market_range_bls() still works, unauthenticated-tier limits apply

    # Offer Check magic-link auth — gates every Claude-calling offercheck endpoint (see app/offercheck/demo_auth.py)
    offercheck_secret_key: str = ""       # OFFERCHECK_SECRET_KEY — HMAC signing key; app refuses to start without it
    offercheck_api_key: str = ""          # OFFERCHECK_API_KEY — separate Anthropic key for offercheck; falls back to anthropic_api_key if unset
    offercheck_internal_key: str = ""     # OFFERCHECK_INTERNAL_KEY — required to mint demo links via POST /auth/demo-link
    offercheck_demo_base_url: str = "http://localhost:5173"  # base URL used to build shareable demo_url values

    # App
    debug: bool = True
    log_level: str = "INFO"


settings = Settings()
