"""Deterministic exposure engine.

The safe / unsafe verdict is computed here from PM2.5 thresholds and simple weather
rules. The language model never decides the verdict; it only explains it.

The thresholds below are PRACTICAL HEURISTICS built on the Indian CPCB PM2.5 bands,
not medical limits. CPCB breakpoints are defined for 24-hour averages; applying them to
hourly forecasts is a simplification. Change THRESHOLDS to try different assumptions.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

PROFILES = ("general", "sensitive")
INTENSITIES = ("light", "vigorous")

# (go_max, caution_max) in ug/m3 of PM2.5
THRESHOLDS = {
    ("general", "light"): (60, 90),
    ("general", "vigorous"): (30, 60),
    ("sensitive", "light"): (30, 60),
    ("sensitive", "vigorous"): (15, 30),
}

# CPCB-style PM2.5 bands (upper bound, label)
BANDS = [
    (30, "Good"),
    (60, "Satisfactory"),
    (90, "Moderate"),
    (120, "Poor"),
    (250, "Very poor"),
    (math.inf, "Severe"),
]

HEAT_C = 38.0
HEAVY_RAIN_MM = 2.0
WALK_M_PER_MIN = 80  # about 4.8 km/h


def thresholds(profile: str, intensity: str) -> tuple[float, float]:
    try:
        return THRESHOLDS[(profile, intensity)]
    except KeyError as exc:
        raise ValueError(f"unknown profile/intensity: {profile}/{intensity}") from exc


def pm25_band(pm25: float | None) -> str:
    if pm25 is None:
        return "Unknown"
    for upper, label in BANDS:
        if pm25 <= upper:
            return label
    return "Severe"


def verdict_for(pm25: float | None, profile: str, intensity: str) -> str:
    if pm25 is None:
        return "unknown"
    go_max, caution_max = thresholds(profile, intensity)
    if pm25 <= go_max:
        return "go"
    if pm25 <= caution_max:
        return "caution"
    return "avoid"


@dataclass
class HourPoint:
    time: str  # local ISO, e.g. 2026-10-10T18:00
    pm25: float | None
    pm10: float | None
    us_aqi: float | None
    temp_c: float | None
    wind_kmh: float | None
    rain_mm: float | None
    daylight: bool
    verdict: str
    band: str
    flags: list[str] = field(default_factory=list)


def _at(arr, i):
    if arr is None or i is None or i < 0 or i >= len(arr):
        return None
    return arr[i]


def _sun_by_date(wx: dict | None) -> dict:
    daily = (wx or {}).get("daily", {})
    out = {}
    for d, sr, ss in zip(daily.get("time", []), daily.get("sunrise", []), daily.get("sunset", [])):
        if sr and ss:
            out[d] = (datetime.fromisoformat(sr), datetime.fromisoformat(ss))
    return out


def _is_daylight(dt: datetime, sun: dict) -> bool:
    mid = dt + timedelta(minutes=30)
    pair = sun.get(dt.date().isoformat())
    if pair:
        return pair[0] <= mid < pair[1]
    return 6 <= dt.hour < 18  # fallback when sunrise/sunset is missing


def build_hours(
    aq: dict,
    wx: dict | None,
    now_local: datetime,
    horizon_hours: int,
    profile: str,
    intensity: str,
) -> list[HourPoint]:
    a = aq.get("hourly", {})
    w = (wx or {}).get("hourly", {})
    wx_index = {t: i for i, t in enumerate(w.get("time", []))}
    sun = _sun_by_date(wx)
    start = now_local.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=horizon_hours)

    hours: list[HourPoint] = []
    for i, t in enumerate(a.get("time", [])):
        dt = datetime.fromisoformat(t)
        if dt < start:
            continue
        if dt >= end:
            break
        j = wx_index.get(t)
        pm25 = _at(a.get("pm2_5"), i)
        temp = _at(w.get("temperature_2m"), j)
        rain = _at(w.get("precipitation"), j)
        flags = []
        if temp is not None and temp >= HEAT_C:
            flags.append("heat")
        if rain is not None and rain >= HEAVY_RAIN_MM:
            flags.append("rain")
        daylight = _is_daylight(dt, sun)
        if not daylight:
            flags.append("dark")
        hours.append(
            HourPoint(
                time=dt.isoformat(timespec="minutes"),
                pm25=pm25,
                pm10=_at(a.get("pm10"), i),
                us_aqi=_at(a.get("us_aqi"), i),
                temp_c=temp,
                wind_kmh=_at(w.get("wind_speed_10m"), j),
                rain_mm=rain,
                daylight=daylight,
                verdict=verdict_for(pm25, profile, intensity),
                band=pm25_band(pm25),
                flags=flags,
            )
        )
    return hours


def _hour_ok(h: HourPoint, allowed: set[str], daylight_only: bool) -> bool:
    if h.verdict not in allowed:
        return False
    if daylight_only and not h.daylight:
        return False
    return "heat" not in h.flags and "rain" not in h.flags


def find_windows(hours: list[HourPoint], allowed: set[str], daylight_only: bool) -> list[dict]:
    windows: list[dict] = []
    cur: list[HourPoint] = []

    def flush() -> None:
        if cur:
            vals = [h.pm25 for h in cur if h.pm25 is not None]
            end = datetime.fromisoformat(cur[-1].time) + timedelta(hours=1)
            windows.append(
                {
                    "start": cur[0].time,
                    "end": end.isoformat(timespec="minutes"),
                    "hours": len(cur),
                    "mean_pm25": round(sum(vals) / len(vals), 1),
                    "max_pm25": round(max(vals), 1),
                }
            )
        cur.clear()

    for h in hours:
        if _hour_ok(h, allowed, daylight_only):
            if cur and datetime.fromisoformat(h.time) - datetime.fromisoformat(cur[-1].time) != timedelta(hours=1):
                flush()
            cur.append(h)
        else:
            flush()
    flush()
    return windows


def best_window(hours: list[HourPoint], daylight_only: bool) -> dict | None:
    level = "go"
    windows = find_windows(hours, {"go"}, daylight_only)
    if not windows:
        level = "caution"
        windows = find_windows(hours, {"go", "caution"}, daylight_only)
    if not windows:
        return None
    best = min(windows, key=lambda w: (w["mean_pm25"], w["start"]))
    return {**best, "level": level}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def rank_parks(parks: list[dict], lat: float, lon: float, radius_m: int, limit: int = 8) -> list[dict]:
    """Nearest first. Air quality is one value per grid cell, so it cannot rank parks
    against each other; distance is what differs. See README for this limitation."""
    out = []
    for p in parks:
        d = haversine_m(lat, lon, p["lat"], p["lon"])
        if d > radius_m:
            continue
        out.append({**p, "distance_m": round(d), "walk_min": max(1, round(d / WALK_M_PER_MIN))})
    out.sort(key=lambda p: p["distance_m"])
    return out[:limit]


def hour_to_dict(h: HourPoint) -> dict:
    return asdict(h)
