
"""Shared access to the existing Roamwise planning engine."""

from typing import Any


def build_plan(
    lat: float,
    lon: float,
    name: str | None,
    profile: str,
    intensity: str,
    horizon: int,
    daylight_only: bool,
) -> dict[str, Any]:
    # Import inside the function to avoid a circular import during startup.
    from .main import _build_plan

    return _build_plan(
        lat=lat,
        lon=lon,
        name=name,
        profile=profile,
        intensity=intensity,
        horizon=horizon,
        daylight_only=daylight_only,
    )


def make_facts(plan: dict[str, Any]) -> dict[str, Any]:
    from .main import _facts

    return _facts(plan)
