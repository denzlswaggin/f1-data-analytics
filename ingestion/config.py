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

    # Data lake. Local by default; set `lake_uri` to an object-store base
    # (e.g. s3://my-bucket/f1-lake or gs://…) to write the Parquet lake to the
    # cloud instead — the ingestion code is storage-agnostic via fsspec. Object
    # stores need the matching extra (`pip install -e ".[cloud]"` for S3) and
    # credentials from the environment (AWS_*, GOOGLE_APPLICATION_CREDENTIALS, …).
    lake_dir: Path = Path("data/raw")
    lake_uri: str = ""

    @property
    def lake_is_remote(self) -> bool:
        """True when the lake lives in an object store (``scheme://…``) not on disk."""
        return "://" in self.lake_uri

    # Jolpica-F1 API
    jolpica_base_url: str = "https://api.jolpi.ca/ergast/f1"
    jolpica_rate_limit_per_sec: float = Field(default=4.0, gt=0)
    jolpica_max_retries: int = Field(default=5, ge=0)

    # FastF1 (Milestone 3)
    fastf1_cache_dir: Path = Path("data/fastf1_cache")
    # Distance grid (metres) for resampling per-lap telemetry — smaller = more
    # rows and finer traces. 25 m ≈ ~200 points per lap.
    fastf1_telemetry_resample_m: float = Field(default=25.0, gt=0)
    # Max sample rate (Hz) kept for positional data (raw.positions). FastF1's
    # native pos_data is ~4-5 Hz; a higher cap keeps it all, a lower one thins it
    # to bound raw size. The browser-facing replay mart is resampled coarser again.
    fastf1_position_rate_hz: float = Field(default=5.0, gt=0)
    # Teleport cutoff for position cleaning: drop a sample if the implied speed from
    # the previous kept sample exceeds this (m/s). Deliberately generous over the
    # ~95 m/s physical max — position-derived speed is noisy (~180 m/s p99.9), while
    # true teleports (garage jumps, GPS glitches) are >1000 m/s, so 300 separates them.
    fastf1_position_max_speed_mps: float = Field(default=300.0, gt=0)
    # Race-replay: how long (s) to keep showing a retired car after it stops moving,
    # before it vanishes from the map. 0 = vanish the instant it stops; a few seconds
    # lets the final resting position settle. The car is retired by *when it actually
    # stops*, not by lap count — this is just the grace/safety window on top.
    replay_retire_buffer_s: float = Field(default=5.0, ge=0)
    # Safety cap (s): never show a retiree more than this long past its last completed
    # lap, even if its position keeps "moving" (a recovery crane/truck follows the car
    # sensor). Bounds the stop-detection above; ~one lap of margin by default.
    replay_retire_max_linger_s: float = Field(default=120.0, gt=0)
    # Overtake detection (analytics.overtakes, over marts.race_replay).
    # Secondary time gate: the interval between the two cars just after a pass must be
    # under this (s) for it to count as a wheel-to-wheel overtake.
    overtake_battle_gap_s: float = Field(default=2.0, gt=0)
    # The passer must stay ahead of the passed car this long (s) after the swap, else
    # it's treated as rank-boundary flicker rather than a completed pass.
    overtake_persist_s: float = Field(default=3.0, ge=0)
    # Skip overtakes before this many seconds — the standing-start order at t≈0 is
    # cosmetic (all cars share lap-progress 0), so ignore the first moments.
    overtake_start_guard_s: float = Field(default=3.0, ge=0)
    # Physical-proximity gate as a fraction of the circuit's bounding-box diagonal:
    # two cars closer than this at the pass count as on-track (a pitting car is far
    # away). Circuit-relative so one value travels between tracks.
    overtake_proximity_frac: float = Field(default=0.02, gt=0)

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
