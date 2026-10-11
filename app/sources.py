
"""External data: Open-Meteo (air quality, weather, geocoding) and OpenStreetMap (parks via Overpass).

All functions return (data, stale). `stale` is True when the live call failed and an
expired cache entry was served.
"""
from __future__ import annotations

import httpx

from . import cache

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WX_URL = "https://api.open-meteo.com/v1/forecast"
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "Roamwise/0.1 (Hacktoberfest 2026 DEV challenge project)"}
TIMEOUT = 25.0


class SourceError(RuntimeError):
    pass


def _request(method: str, url: str, **kwargs):
    try:
        resp = httpx.request(method, url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SourceError(f"{url}: {exc}") from exc


def _cached(key: str, ttl: int, fetch):
    hit = cache.get(key)
    if hit is not None:
        return hit, False
    try:
        data = fetch()
    except SourceError:
        stale = cache.get(key, allow_stale=True)
        if stale is not None:
            return stale, True
        raise
    cache.set(key, data, ttl)
    return data, False


def fetch_air_quality(lat: float, lon: float):
    def go():
        return _request(
            "GET",
            AQ_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "pm2_5,pm10,us_aqi",
                "timezone": "auto",
                "forecast_days": 3,
            },
        )

    return _cached(f"aq:{round(lat, 2)}:{round(lon, 2)}", 30 * 60, go)


def fetch_weather(lat: float, lon: float):
    def go():
        return _request(
            "GET",
            WX_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
                "daily": "sunrise,sunset",
                "timezone": "auto",
                "forecast_days": 3,
            },
        )

    return _cached(f"wx:{round(lat, 2)}:{round(lon, 2)}", 30 * 60, go)


def geocode(query: str):
    def go():
        data = _request("GET", GEO_URL, params={"name": query, "count": 6, "language": "en", "format": "json"})
        return [
            {
                "name": r.get("name"),
                "admin1": r.get("admin1"),
                "country": r.get("country"),
                "lat": r.get("latitude"),
                "lon": r.get("longitude"),
            }
            for r in data.get("results", [])
        ]

    return _cached(f"geo:{query.strip().lower()}", 7 * 24 * 3600, go)


def fetch_parks(lat: float, lon: float, radius_m: int = 3000):
    """Named parks, gardens and nature reserves around a point, from OpenStreetMap."""
    clat, clon = round(lat, 2), round(lon, 2)

    def go():
        query = (
            f"[out:json][timeout:25];"
            f'nwr["leisure"~"^(park|garden|nature_reserve)$"]["name"]'
            f"(around:{radius_m},{clat},{clon});out center 120;"
        )
        last_error: Exception | None = None
        for url in OVERPASS_URLS:
            try:
                data = _request("POST", url, data={"data": query})
                break
            except SourceError as exc:
                last_error = exc
        else:
            raise SourceError(str(last_error))

        seen, parks = set(), []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name:en") or tags.get("name")
            if el.get("type") == "node":
                plat, plon = el.get("lat"), el.get("lon")
            else:
                center = el.get("center") or {}
                plat, plon = center.get("lat"), center.get("lon")
            if not name or plat is None or plon is None:
                continue
            key = (name.lower(), round(plat, 3), round(plon, 3))
            if key in seen:
                continue
            seen.add(key)
            parks.append(
                {
                    "name": name,
                    "kind": tags.get("leisure"),
                    "lat": plat,
                    "lon": plon,
                    "osm_url": f"https://www.openstreetmap.org/?mlat={plat}&mlon={plon}#map=17/{plat}/{plon}",
                }
            )
        return parks

    return _cached(f"parks:{clat}:{clon}:{radius_m}", 24 * 3600, go)
