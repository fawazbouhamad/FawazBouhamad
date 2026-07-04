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
DEFAULT_DAYS = 2  # two days is enough for an operational cooling plan


def fetch_open_meteo(latitude: float, longitude: float, days: int = DEFAULT_DAYS) -> WeatherSeries:
    """Fetch an hourly temperature forecast from Open-Meteo (no key).

    apparent_temperature is requested as a free humidity proxy. Raises on
    any network/format problem; callers should fall back to
    synthetic_kuwait_hot_day().
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,apparent_temperature",
        "forecast_days": days,
        "timezone": "auto",
    }
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    hours = days * 24
    times = data["hourly"]["time"][:hours]
    temps = data["hourly"]["temperature_2m"][:hours]
    apparent = (data["hourly"].get("apparent_temperature") or [None] * len(times))[:hours]
    if not times or len(times) != len(temps) or any(t is None for t in temps):
        raise ValueError("Open-Meteo returned an incomplete series")

    points = [
        WeatherPoint(time=t, temp_c=float(v), apparent_temp_c=a)
        for t, v, a in zip(times, temps, apparent)
    ]
    return WeatherSeries(
        source="open-meteo",
        is_live=True,
        points=points,
        note=f"Live {days*24}h forecast from Open-Meteo (free, no API key).",
    )


def synthetic_kuwait_hot_day(start: datetime | None = None, days: int = DEFAULT_DAYS) -> WeatherSeries:
    """Generate a plausible extreme Kuwait summer period, hourly points.

    Sinusoidal daily profile: minimum ~33 C around 05:00, maximum ~48 C
    around 15:00, with a small deterministic day-to-day variation. Apparent
    temperature is temp + 1.8 C as a crude coastal-humidity proxy. Used
    when live APIs are unreachable. Starts at local midnight so every day
    is a complete calendar day.
    """
    if start is None:
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    points: list[WeatherPoint] = []
    for i in range(days * 24):
        ts = start + timedelta(hours=i)
        hour, day_idx = ts.hour, i // 24
        mean = 40.5 + 1.2 * math.sin(1.1 * day_idx)  # mild day-to-day wave
        amplitude = 7.5
        # Peak at 15:00 -> cos phase shifted so hour==15 gives +amplitude.
        temp = mean + amplitude * math.cos((hour - 15) / 24 * 2 * math.pi)
        points.append(
            WeatherPoint(
                time=ts.isoformat(timespec="hours"),
                temp_c=round(temp, 1),
                apparent_temp_c=round(temp + 1.8, 1),
            )
        )

    return WeatherSeries(
        source="synthetic-kuwait-hot-day",
        is_live=False,
        points=points,
        note=(
            "Synthetic extreme Kuwait summer period (offline fallback). "
            "Live Open-Meteo data was unavailable."
        ),
    )


def get_weather(latitude: float, longitude: float, days: int = DEFAULT_DAYS) -> WeatherSeries:
    """Best-effort weather: live Open-Meteo, else synthetic fallback."""
    try:
        return fetch_open_meteo(latitude, longitude, days=days)
    except Exception:
        return synthetic_kuwait_hot_day(days=days)
