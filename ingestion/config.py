"""Central configuration, loaded from environment / .env via pydantic-settings.

All settings are prefixed ``F1_`` so they don't collide with other tooling.
See ``.env.example`` for the full list.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

WarehouseKind = Literal["duckdb", "postgres"]


class Settings(BaseSettings):
    """Runtime configuration for ingestion and loading."""

    model_config = SettingsConfigDict(
        env_prefix="F1_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Warehouse selection
    warehouse: WarehouseKind = "duckdb"

    # DuckDB (dev)
    duckdb_path: Path = Path("data/warehouse/f1.duckdb")

    # Postgres (prod)
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "f1"
    pg_user: str = "f1"
    pg_password: str = "f1"
    pg_schema: str = "raw"

    # Data lake
    lake_dir: Path = Path("data/raw")

    # Jolpica-F1 API
    jolpica_base_url: str = "https://api.jolpi.ca/ergast/f1"
    jolpica_rate_limit_per_sec: float = Field(default=4.0, gt=0)
    jolpica_max_retries: int = Field(default=5, ge=0)

    # FastF1 (Milestone 3)
    fastf1_cache_dir: Path = Path("data/fastf1_cache")

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    @property
    def pg_dsn(self) -> str:
        """SQLAlchemy connection string for the Postgres warehouse."""
        return (
            f"postgresql+psycopg2://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
