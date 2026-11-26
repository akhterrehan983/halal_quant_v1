from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Halal Quant API"
    version: str = "0.2.0"
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"
    starting_cash: float = 100_000.0
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    csv_max_upload_mb: int = 25
    import_conflict_policy: str = "skip"  # reject | skip | update
    # Extra benchmark / index-proxy symbols (comma-separated). Registered benchmarks are never scanned
    # or traded as equities. NIFTY500_PROXY is built in; see app/market_data/benchmarks.py.
    benchmark_symbols: str = Field(default="", validation_alias="BENCHMARK_SYMBOLS")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_enabled(self) -> bool:
        return bool(self.database_url and self.database_url.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()