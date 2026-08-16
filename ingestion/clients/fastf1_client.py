"""Client for FastF1 — per-lap timing and tyre data from the official F1 feed.

FastF1 covers 2018→present, downloads a lot per session, and caches to disk, so
this client enables the cache and exposes focused loaders — per-lap records
(with tyre + speed-trap context), per-minute weather, and distance-resampled
telemetry — each flattened to compact, warehouse-friendly rows.

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
                # Session time at which the lap began — lets weather be joined by
                # time later (v1 marts join at race grain).
                "lap_start_sec": _seconds(laps["LapStartTime"]),
                # Speed-trap readings (km/h): two intermediate points, the finish
                # line, and the longest straight (SpeedST = straight-line speed).
                "speed_i1_kph": laps["SpeedI1"],
                "speed_i2_kph": laps["SpeedI2"],
                "speed_fl_kph": laps["SpeedFL"],
                "speed_st_kph": laps["SpeedST"],
            }
        )
        for src, dst in _TIMEDELTA_COLS.items():
            out[dst] = _seconds(laps[src])

        # In/out laps without a set time arrive as NaT; `_seconds` maps those to
        # NaN here. The raw layer keeps every lap (stint-boundary rows included);
        # null lap times are filtered later in `mart_lap_times`.
        out = out.reset_index(drop=True)
        log.info(
            "fastf1.laps",
            season=season,
            round=rnd,
            session=session,
            rows=len(out),
        )
        return out

    def load_session_weather(self, season: int, rnd: int, session: str = "R") -> pd.DataFrame:
        """Return one row per weather sample (roughly per minute) for a session."""
        ff1 = self._ensure_loaded()
        sess = ff1.get_session(season, rnd, session)
        sess.load(laps=False, telemetry=False, weather=True, messages=False)
        weather = sess.weather_data
        if weather is None or weather.empty:
            log.warning("fastf1.no_weather", season=season, round=rnd, session=session)
            return pd.DataFrame()

        out = pd.DataFrame(
            {
                "season": season,
                "round": rnd,
                "session": session,
                "time_sec": _seconds(weather["Time"]),
                "air_temp": weather["AirTemp"],
                "track_temp": weather["TrackTemp"],
                "humidity": weather["Humidity"],
                "pressure": weather["Pressure"],
                "wind_speed": weather["WindSpeed"],
                "wind_direction": weather["WindDirection"],
                # FastF1 Rainfall is already a boolean.
                "is_raining": weather["Rainfall"],
            }
        ).reset_index(drop=True)
        log.info("fastf1.weather", season=season, round=rnd, session=session, rows=len(out))
        return out
