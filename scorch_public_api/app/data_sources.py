"""Free/open weather data sources for SCORCH.

Priority:
  1. Open-Meteo forecast API (free, no API key).
  2. Synthetic Kuwait hot-day generator (offline fallback) so the app
     always works, even with no network.

NASA POWER is another free option for solar/climatology variables; it is a
documented Level-0.5 upgrade but not required for the MVP, so we keep a
single live source plus a robust fallback.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import httpx

from .models import WeatherPoint, WeatherSeries

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_HOURS = 48  # two days is enough for an operational cooling plan


def fetch_open_meteo(latitude: float, longitude: float) -> WeatherSeries:
    """Fetch a 48h hourly temperature forecast from Open-Meteo (no key).

    Raises on any network/format problem; callers should fall back to
    synthetic_kuwait_hot_day().
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m",
        "forecast_days": 2,
        "timezone": "auto",
    }
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    times = data["hourly"]["time"][:FORECAST_HOURS]
    temps = data["hourly"]["temperature_2m"][:FORECAST_HOURS]
    if not times or len(times) != len(temps) or any(t is None for t in temps):
        raise ValueError("Open-Meteo returned an incomplete series")

    points = [WeatherPoint(time=t, temp_c=float(v)) for t, v in zip(times, temps)]
    return WeatherSeries(
        source="open-meteo",
        is_live=True,
        points=points,
        note="Live 48h forecast from Open-Meteo (free, no API key).",
    )


def synthetic_kuwait_hot_day(start: datetime | None = None) -> WeatherSeries:
    """Generate a plausible extreme Kuwait summer day, 48 hourly points.

    Sinusoidal profile: minimum ~33 C around 05:00, maximum ~48 C around
    15:00, second day slightly hotter. Used when live APIs are unreachable.
    """
    if start is None:
        start = datetime.now().replace(minute=0, second=0, microsecond=0)

    points: list[WeatherPoint] = []
    for i in range(FORECAST_HOURS):
        ts = start + timedelta(hours=i)
        hour = ts.hour
        day_boost = 0.8 if i >= 24 else 0.0  # day 2 marginally hotter
        mean, amplitude = 40.5, 7.5
        # Peak at 15:00 -> cos phase shifted so hour==15 gives +amplitude.
        temp = mean + amplitude * math.cos((hour - 15) / 24 * 2 * math.pi) + day_boost
        points.append(WeatherPoint(time=ts.isoformat(timespec="hours"), temp_c=round(temp, 1)))

    return WeatherSeries(
        source="synthetic-kuwait-hot-day",
        is_live=False,
        points=points,
        note=(
            "Synthetic extreme Kuwait summer day (offline fallback). "
            "Live Open-Meteo data was unavailable."
        ),
    )


def get_weather(latitude: float, longitude: float) -> WeatherSeries:
    """Best-effort weather: live Open-Meteo, else synthetic fallback."""
    try:
        return fetch_open_meteo(latitude, longitude)
    except Exception:
        return synthetic_kuwait_hot_day()
