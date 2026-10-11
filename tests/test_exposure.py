from datetime import datetime, timedelta

import pytest

from app import exposure


def make_aq(start: datetime, pm_values):
    times = [
        (start + timedelta(hours=i)).isoformat(timespec="minutes")
        for i in range(len(pm_values))
    ]

    return {
        "utc_offset_seconds": 0,
        "hourly": {
            "time": times,
            "pm2_5": pm_values,
            "pm10": pm_values,
            "us_aqi": pm_values,
        },
    }


def make_wx(start: datetime, count, temp=30.0, rain=0.0):
    times = [
        (start + timedelta(hours=i)).isoformat(timespec="minutes")
        for i in range(count)
    ]
    day = start.date().isoformat()

    return {
        "hourly": {
            "time": times,
            "temperature_2m": [temp] * count,
            "precipitation": [rain] * count,
            "wind_speed_10m": [5.0] * count,
            "relative_humidity_2m": [50] * count,
        },
        "daily": {
            "time": [day],
            "sunrise": [f"{day}T06:00"],
            "sunset": [f"{day}T18:00"],
        },
    }


@pytest.mark.parametrize(
    ("pm25", "profile", "intensity", "expected"),
    [
        (60, "general", "light", "go"),
        (61, "general", "light", "caution"),
        (90, "general", "light", "caution"),
        (91, "general", "light", "avoid"),
        (30, "sensitive", "light", "go"),
        (31, "sensitive", "light", "caution"),
        (61, "sensitive", "light", "avoid"),
        (None, "general", "light", "unknown"),
    ],
)
def test_verdict_thresholds(pm25, profile, intensity, expected):
    assert exposure.verdict_for(pm25, profile, intensity) == expected


def test_sensitive_vigorous_profile_is_stricter():
    assert exposure.verdict_for(40, "general", "light") == "go"
    assert exposure.verdict_for(40, "sensitive", "vigorous") == "avoid"


@pytest.mark.parametrize(
    ("pm25", "expected"),
    [
        (20, "Good"),
        (30, "Good"),
        (31, "Satisfactory"),
        (60, "Satisfactory"),
        (61, "Moderate"),
        (90, "Moderate"),
        (91, "Poor"),
        (150, "Very poor"),
        (250, "Very poor"),
        (251, "Severe"),
        (400, "Severe"),
        (None, "Unknown"),
    ],
)
def test_pm25_band_labels(pm25, expected):
    assert exposure.pm25_band(pm25) == expected


def test_unknown_profile_raises():
    with pytest.raises(ValueError):
        exposure.thresholds("nobody", "light")


def test_unknown_intensity_raises():
    with pytest.raises(ValueError):
        exposure.thresholds("general", "running")


def test_best_window_selects_cleanest_daylight_stretch():
    start = datetime(2026, 10, 10, 6, 0)
    pm25 = [200, 150, 55, 40, 35, 120, 58, 59]

    hours = exposure.build_hours(
        make_aq(start, pm25),
        make_wx(start, len(pm25)),
        start,
        8,
        "general",
        "light",
    )

    best = exposure.best_window(hours, daylight_only=True)

    assert best is not None
    assert best["level"] == "go"
    assert best["start"] == "2026-10-10T08:00"
    assert best["end"] == "2026-10-10T11:00"
    assert best["hours"] == 3


def test_daylight_only_excludes_night_hours():
    start = datetime(2026, 10, 10, 18, 0)

    hours = exposure.build_hours(
        make_aq(start, [10, 10, 10]),
        make_wx(start, 3),
        start,
        3,
        "general",
        "light",
    )

    assert exposure.best_window(hours, daylight_only=True) is None
    assert exposure.best_window(hours, daylight_only=False) is not None


def test_heavy_rain_blocks_outdoor_window():
    start = datetime(2026, 10, 10, 9, 0)

    hours = exposure.build_hours(
        make_aq(start, [10, 10]),
        make_wx(start, 2, rain=3.0),
        start,
        2,
        "general",
        "light",
    )

    assert exposure.best_window(hours, daylight_only=True) is None


def test_extreme_heat_blocks_outdoor_window():
    start = datetime(2026, 10, 10, 9, 0)

    hours = exposure.build_hours(
        make_aq(start, [10, 10]),
        make_wx(start, 2, temp=40.0),
        start,
        2,
        "general",
        "light",
    )

    assert exposure.best_window(hours, daylight_only=True) is None


def test_caution_window_is_used_when_no_go_window_exists():
    start = datetime(2026, 10, 10, 9, 0)

    hours = exposure.build_hours(
        make_aq(start, [80, 85]),
        make_wx(start, 2),
        start,
        2,
        "general",
        "light",
    )

    best = exposure.best_window(hours, daylight_only=True)

    assert best is not None
    assert best["level"] == "caution"


def test_no_window_when_all_hours_are_unsafe():
    start = datetime(2026, 10, 10, 9, 0)

    hours = exposure.build_hours(
        make_aq(start, [300, 320]),
        make_wx(start, 2),
        start,
        2,
        "general",
        "light",
    )

    assert exposure.best_window(hours, daylight_only=True) is None


def test_missing_weather_still_produces_exposure_results():
    start = datetime(2026, 10, 10, 9, 0)

    hours = exposure.build_hours(
        make_aq(start, [20, 25]),
        None,
        start,
        2,
        "general",
        "light",
    )

    assert [hour.verdict for hour in hours] == ["go", "go"]
    assert all(hour.daylight for hour in hours)


def test_parks_are_ranked_by_distance_and_filtered_by_radius():
    parks = [
        {"name": "Far", "lat": 28.70, "lon": 77.21},
        {"name": "Near", "lat": 28.615, "lon": 77.21},
    ]

    ranked = exposure.rank_parks(
        parks,
        28.6139,
        77.2090,
        radius_m=3000,
    )

    assert [park["name"] for park in ranked] == ["Near"]
    assert ranked[0]["distance_m"] > 0
    assert ranked[0]["walk_min"] >= 1


def test_park_results_respect_limit():
    parks = [
        {
            "name": f"Park {i}",
            "lat": 28.6139 + (i * 0.0001),
            "lon": 77.2090,
        }
        for i in range(10)
    ]

    ranked = exposure.rank_parks(
        parks,
        28.6139,
        77.2090,
        radius_m=3000,
        limit=3,
    )

    assert len(ranked) == 3
