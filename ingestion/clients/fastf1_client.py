"""Client for FastF1 — per-lap timing and tyre data from the official F1 feed.

FastF1 covers 2018→present, downloads a lot per session, and caches to disk, so
this client enables the cache and exposes one focused loader: per-lap records for
a session (race or qualifying), flattened to compact, warehouse-friendly rows.

``fastf1`` is imported lazily (it is a heavy optional dependency; install with
``pip install -e ".[telemetry]"``).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ingestion.config import Settings, get_settings
from ingestion.logging import get_logger

log = get_logger(__name__)

# Timedelta columns to convert to float seconds.
_TIMEDELTA_COLS = {
    "LapTime": "lap_time_sec",
    "Sector1Time": "sector1_sec",
    "Sector2Time": "sector2_sec",
    "Sector3Time": "sector3_sec",
}


def _seconds(series: pd.Series) -> pd.Series:
    return series.dt.total_seconds()


class FastF1Client:
    """Loads and flattens FastF1 session lap data."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._fastf1: Any = None

    def _ensure_loaded(self) -> Any:
        if self._fastf1 is None:
            import fastf1 as _fastf1

            self.settings.fastf1_cache_dir.mkdir(parents=True, exist_ok=True)
            _fastf1.Cache.enable_cache(str(self.settings.fastf1_cache_dir))
            self._fastf1 = _fastf1
        return self._fastf1

    def load_session_laps(self, season: int, rnd: int, session: str = "R") -> pd.DataFrame:
        """Return one row per driver per lap for a session.

        ``session`` is a FastF1 identifier: 'R' (race), 'Q' (qualifying),
        'S' (sprint), etc.
        """
        ff1 = self._ensure_loaded()
        sess = ff1.get_session(season, rnd, session)
        sess.load(laps=True, telemetry=False, weather=False, messages=False)
        laps = sess.laps
        if laps is None or laps.empty:
            log.warning("fastf1.no_laps", season=season, round=rnd, session=session)
            return pd.DataFrame()

        out = pd.DataFrame(
            {
                "season": season,
                "round": rnd,
                "session": session,
                "driver_code": laps["Driver"],
                "driver_number": laps["DriverNumber"],
                "team": laps["Team"],
                "lap_number": laps["LapNumber"].astype("Int64"),
                "stint": laps["Stint"].astype("Int64"),
                "compound": laps["Compound"],
                "tyre_life": laps["TyreLife"].astype("Int64"),
                "is_fresh_tyre": laps["FreshTyre"],
                "position": laps["Position"].astype("Int64"),
                "is_personal_best": laps["IsPersonalBest"],
                "track_status": laps["TrackStatus"].astype("string"),
            }
        )
        for src, dst in _TIMEDELTA_COLS.items():
            out[dst] = _seconds(laps[src])

        # Drop laps with no time (e.g. in/out laps without a set time have NaT).
        out = out.reset_index(drop=True)
        log.info(
            "fastf1.laps",
            season=season,
            round=rnd,
            session=session,
            rows=len(out),
        )
        return out
