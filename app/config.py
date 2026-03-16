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

    # App
    debug: bool = True
    log_level: str = "INFO"


settings = Settings()
