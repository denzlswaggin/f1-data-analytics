"""Client for FastF1 — per-lap timing and tyre data from the official F1 feed.

FastF1 covers 2018→present, downloads a lot per session, and caches to disk, so
this client enables the cache and exposes focused loaders — per-lap records
(with tyre + speed-trap context), per-minute weather, distance-resampled
telemetry, and time-stamped positional data (for the race-replay map) — each
flattened to compact, warehouse-friendly rows.

``fastf1`` is imported lazily (it is a heavy optional dependency; install with
``pip install -e ".[telemetry]"``).
"""

from __future__ import annotations

from typing import Any

import numpy as np
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


def resample_lap_telemetry(tel: pd.DataFrame, step_m: float) -> pd.DataFrame:
    """Resample one lap's telemetry onto a uniform distance grid.

    Continuous channels (speed, throttle, rpm, x, y) are linearly interpolated;
    discrete channels (brake, DRS, gear) are interpolated then rounded to the
    nearest integer. Returns an empty frame when the lap has no usable distance
    axis (e.g. an in/out lap with missing telemetry). Pure (no FastF1) so it can
    be unit-tested on a synthetic frame.
    """
    if tel.empty or "Distance" not in tel.columns:
        return pd.DataFrame()
    distance = tel["Distance"].to_numpy(dtype="float64")
    finite = np.isfinite(distance)
    if int(finite.sum()) < 2:
        return pd.DataFrame()
    order = np.argsort(distance[finite])
    xp = distance[finite][order]
    d_max = float(xp[-1])
    if d_max <= 0:
        return pd.DataFrame()
    grid = np.arange(0.0, d_max, step_m)

    def _interp(col: str) -> Any:
        fp = tel[col].to_numpy(dtype="float64")[finite][order]
        return np.interp(grid, xp, fp)

    return pd.DataFrame(
        {
            "distance_m": grid,
            "speed_kph": _interp("Speed"),
            "throttle": _interp("Throttle"),
            "rpm": _interp("RPM"),
            "x": _interp("X"),
            "y": _interp("Y"),
            "brake": np.rint(_interp("Brake")).astype("int64"),
            "drs": np.rint(_interp("DRS")).astype("int64"),
            "gear": np.rint(_interp("nGear")).astype("int64"),
        }
    )


def thin_positions(
    df: pd.DataFrame, rate_hz: float, time_col: str = "session_time_sec"
) -> pd.DataFrame:
    """Thin time-ordered position samples to at most ``rate_hz`` samples/second.

    Rows are sorted by ``time_col`` (dropping non-finite times), then the first
    sample in each ``1/rate_hz`` time bucket is kept. FastF1's native pos_data is
    ~4-5 Hz, so a higher cap is a no-op; a lower cap decimates deterministically.
    Pure (no FastF1) so it can be unit-tested on a synthetic frame.
    """
    if df.empty or rate_hz <= 0:
        return df.reset_index(drop=True)
    t = df[time_col].to_numpy(dtype="float64")
    finite = np.isfinite(t)
    df = df.loc[finite]
    t = t[finite]
    if len(t) == 0:
        return df.reset_index(drop=True)
    order = np.argsort(t, kind="stable")
    df = df.iloc[order].reset_index(drop=True)
    bucket = np.floor(t[order] * rate_hz).astype("int64")
    keep = np.concatenate(([True], np.diff(bucket) != 0))
    return df.iloc[keep].reset_index(drop=True)


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

    def load_session_telemetry(self, season: int, rnd: int, session: str = "R") -> pd.DataFrame:
        """Return distance-resampled car telemetry: one row per driver/lap/point.

        Heavy: FastF1 downloads full-resolution telemetry per lap; this resamples
        each lap onto the configured distance grid to keep the warehouse compact.
        """
        ff1 = self._ensure_loaded()
        sess = ff1.get_session(season, rnd, session)
        sess.load(laps=True, telemetry=True, weather=False, messages=False)
        laps = sess.laps
        if laps is None or laps.empty:
            log.warning("fastf1.no_laps_for_telemetry", season=season, round=rnd, session=session)
            return pd.DataFrame()

        step = float(self.settings.fastf1_telemetry_resample_m)
        frames: list[pd.DataFrame] = []
        for _, lap in laps.iterlaps():
            try:
                tel = lap.get_telemetry()
            except Exception as exc:
                log.debug("fastf1.telemetry_lap_skip", season=season, round=rnd, error=str(exc))
                continue
            resampled = resample_lap_telemetry(tel, step)
            if resampled.empty:
                continue
            lap_number = lap["LapNumber"]
            resampled.insert(0, "season", season)
            resampled.insert(1, "round", rnd)
            resampled.insert(2, "session", session)
            resampled.insert(3, "driver_code", lap["Driver"])
            resampled.insert(4, "lap_number", int(lap_number) if pd.notna(lap_number) else pd.NA)
            frames.append(resampled)

        if not frames:
            log.warning("fastf1.no_telemetry", season=season, round=rnd, session=session)
            return pd.DataFrame()

        out = pd.concat(frames, ignore_index=True)
        log.info("fastf1.telemetry", season=season, round=rnd, session=session, rows=len(out))
        return out

    def load_session_position(self, season: int, rnd: int, session: str = "R") -> pd.DataFrame:
        """Return time-stamped car position: one row per driver per position sample.

        Uses FastF1's positional feed (``session.pos_data``), which carries X/Y in
        the track reference frame stamped with ``SessionTime`` — the shared clock
        that lets every car be placed at the same instant (unlike the
        distance-gridded telemetry). Samples are thinned to
        ``settings.fastf1_position_rate_hz``. Heavy: requires a full telemetry load.
        """
        ff1 = self._ensure_loaded()
        sess = ff1.get_session(season, rnd, session)
        sess.load(laps=True, telemetry=True, weather=False, messages=False)
        pos_data = getattr(sess, "pos_data", None)
        if not pos_data:
            log.warning("fastf1.no_pos_data", season=season, round=rnd, session=session)
            return pd.DataFrame()

        rate = float(self.settings.fastf1_position_rate_hz)
        frames: list[pd.DataFrame] = []
        for number, pos in pos_data.items():
            if pos is None or pos.empty or "SessionTime" not in pos.columns:
                continue
            try:
                code = str(sess.get_driver(number)["Abbreviation"])
            except Exception:  # missing driver metadata — fall back to the number
                code = str(number)
            frame = pd.DataFrame(
                {
                    "season": season,
                    "round": rnd,
                    "session": session,
                    "driver_code": code,
                    "session_time_sec": _seconds(pos["SessionTime"]),
                    "x": pos["X"].to_numpy(dtype="float64"),
                    "y": pos["Y"].to_numpy(dtype="float64"),
                    "status": pos["Status"].astype("string"),
                }
            )
            frames.append(thin_positions(frame, rate))

        if not frames:
            log.warning("fastf1.no_positions", season=season, round=rnd, session=session)
            return pd.DataFrame()

        out = pd.concat(frames, ignore_index=True)
        log.info("fastf1.positions", season=season, round=rnd, session=session, rows=len(out))
        return out
