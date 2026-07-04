"""7-day heat/cooling outlook for a built-in example asset.

Runs the Level-0 risk pipeline day-by-day over a 7-day public forecast
(Open-Meteo, else the synthetic Kuwait fallback). Screening-grade only.
"""

from __future__ import annotations

from . import risk_model
from .data_sources import get_weather
from .map_layers import asset_to_request, get_asset_or_404
from .models import (
    ActionRequest,
    DailyOutlook,
    WeatherSeries,
    WeeklyOutlookResponse,
)
from .recommendations import build_action_plan

OUTLOOK_DAYS = 7
MIN_HOURS_PER_DAY = 20  # skip partial first/last days from live feeds


def _split_by_day(weather: WeatherSeries) -> list[tuple[str, list]]:
    """Group hourly points into complete calendar days, in order."""
    by_day: dict[str, list] = {}
    for p in weather.points:
        by_day.setdefault(p.time[:10], []).append(p)
    return [(d, pts) for d, pts in by_day.items() if len(pts) >= MIN_HOURS_PER_DAY]


def build_weekly_outlook(asset_slug: str) -> WeeklyOutlookResponse:
    asset = get_asset_or_404(asset_slug)
    req = asset_to_request(asset)
    weather = get_weather(req.latitude, req.longitude, days=OUTLOOK_DAYS)

    days: list[DailyOutlook] = []
    for date, pts in _split_by_day(weather)[:OUTLOOK_DAYS]:
        day_series = WeatherSeries(
            source=weather.source, is_live=weather.is_live, points=pts, note=weather.note
        )
        risk = risk_model.compute_heat_risk(req, day_series)
        demand = risk_model.estimate_demand(req, day_series)
        window = risk_model.peak_cooling_window(demand)
        plan = build_action_plan(
            ActionRequest(
                risk_score=risk["score"],
                building_type=req.building_type,
                peak_window_start_hour=window.start_hour,
                peak_window_end_hour=min(window.end_hour, 24),
            )
        )
        apparent = [p.apparent_temp_c for p in pts if p.apparent_temp_c is not None]
        days.append(
            DailyOutlook(
                date=date,
                max_temp_c=risk["max_temp_c"],
                max_apparent_temp_c=max(apparent) if apparent else None,
                cooling_degree_hours=risk["cooling_degree_hours"],
                heat_risk_score=risk["score"],
                risk_category=risk["category"],
                peak_cooling_window=window,
                recommended_action_summary=(
                    f"{risk['category']} risk: pre-cool "
                    f"{plan.pre_cooling_window.split(' (')[0]}; protect "
                    f"{window.start_hour:02d}:00-{window.end_hour:02d}:00."
                ),
            )
        )

    return WeeklyOutlookResponse(
        asset_slug=asset_slug,
        asset_name=asset["name"],
        weather_source=weather.source,
        is_live=weather.is_live,
        days=days,
        confidence=risk_model.confidence_level(weather),
        assumptions=risk_model.model_assumptions(req, weather)
        + ["Daily risk scores use each calendar day's hourly forecast independently."],
    )
