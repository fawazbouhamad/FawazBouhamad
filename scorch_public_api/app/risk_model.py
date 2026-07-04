"""SCORCH heat-risk and cooling-demand models (Level 0, public data only).

Deliberately simple and fully transparent:

  cooling_degree      = max(outdoor_temp_c - BASE_TEMP_C, 0)
  cooling_load_mw     = area_m2 * cooling_intensity_kw_m2
                        * cooling_degree_factor * occupancy_factor / 1000
  total_demand_mw     = base_load_mw + occupancy_load_mw
                        + cooling_load_mw + event_load_mw

Every number that goes into a response is an assumption-driven screening
estimate. The assumptions are returned alongside the results.
"""

from __future__ import annotations

from datetime import datetime

from .assets import ARCHETYPES, OCCUPANCY_FACTORS
from .models import (
    AssetRequest,
    PeakWindow,
    ScenarioSeries,
    WeatherSeries,
)

BASE_TEMP_C = 24.0          # balance point: no mechanical cooling needed below this
REFERENCE_COOLING_DEGREE = 20.0  # cooling_degree at which intensity = nameplate
EXTREME_HEAT_C = 45.0       # equipment-stress threshold for GCC plant
STRESS_TEMP_CAP = 1.30      # cooling_degree_factor cap (plant saturates)

RISK_CATEGORIES = [
    (30, "Low"),
    (55, "Moderate"),
    (75, "High"),
    (100, "Very High"),
]


def risk_category(score: float) -> str:
    for upper, label in RISK_CATEGORIES:
        if score <= upper:
            return label
    return "Very High"


def _hour_of(point_time: str) -> int:
    return datetime.fromisoformat(point_time).hour


def cooling_degree_hours(temps: list[float]) -> float:
    return sum(max(t - BASE_TEMP_C, 0.0) for t in temps)


def occupancy_profile(hour: int, req: AssetRequest) -> float:
    """0..1 occupancy fraction for a given local hour.

    Simple ramp: builds after opening, peaks late afternoon/evening for
    retail-style buildings, zero when closed. Screening-grade only.
    """
    oh = req.operating_hours
    if not (oh.start_hour <= hour < oh.end_hour):
        return 0.0
    span = oh.end_hour - oh.start_hour
    progress = (hour - oh.start_hour) / span
    # Ramp up to ~1.0 around 60-80% through the day, taper at close.
    if progress < 0.25:
        base = 0.4 + 1.6 * progress          # 0.4 -> 0.8
    elif progress < 0.8:
        base = 0.8 + 0.36 * (progress - 0.25)  # 0.8 -> 1.0
    else:
        base = 1.0 - 1.5 * (progress - 0.8)    # taper to ~0.7
    return max(0.0, min(1.0, base))


def zone_internal_load_multiplier(req: AssetRequest) -> float:
    """Area-weighted internal load factor from zones (1.0 if none given)."""
    if not req.zones:
        return 1.0
    total_share = sum(z.area_share for z in req.zones)
    if total_share <= 0:
        return 1.0
    weighted = sum(z.area_share * z.internal_load_factor for z in req.zones)
    return weighted / total_share


def compute_heat_risk(req: AssetRequest, weather: WeatherSeries) -> dict:
    """Heat risk score 0-100 from public weather + archetype sensitivity."""
    arch = ARCHETYPES[req.building_type]
    temps = [p.temp_c for p in weather.points]
    hours = [_hour_of(p.time) for p in weather.points]

    max_temp = max(temps)
    cdh = cooling_degree_hours(temps)
    hours_above_45 = sum(1 for t in temps if t >= EXTREME_HEAT_C)

    # Component 1: peak temperature severity (0-35). 35C -> 0, 50C -> 35.
    c_max = max(0.0, min(35.0, (max_temp - 35.0) / 15.0 * 35.0))

    # Component 2: sustained heat via cooling degree hours (0-25).
    # A brutal Kuwait 48h period reaches ~700-800 CDH.
    c_cdh = max(0.0, min(25.0, cdh / 700.0 * 25.0))

    # Component 3: extreme-heat equipment stress hours (0-15).
    c_stress = min(15.0, hours_above_45 * 2.0)

    # Component 4: overlap of operating hours with the hottest 6 hours (0-15).
    hottest_idx = sorted(range(len(temps)), key=lambda i: temps[i], reverse=True)[:6]
    oh = req.operating_hours
    overlap = sum(1 for i in hottest_idx if oh.start_hour <= hours[i] < oh.end_hour)
    c_overlap = overlap / 6.0 * 15.0

    # Component 5: event/occupancy modifier (-3 to +10).
    c_mod = (5.0 if req.event_day else 0.0)
    c_mod += {"low": -3.0, "medium": 0.0, "high": 5.0}[req.occupancy_level]

    raw = (c_max + c_cdh + c_stress + c_overlap + c_mod) * arch["heat_sensitivity"]
    score = round(max(0.0, min(100.0, raw)), 1)

    return {
        "score": score,
        "category": risk_category(score),
        "max_temp_c": max_temp,
        "cooling_degree_hours": round(cdh, 1),
        "hours_above_45c": hours_above_45,
        "components": {
            "max_temperature": round(c_max, 1),
            "cooling_degree_hours": round(c_cdh, 1),
            "extreme_heat_stress": round(c_stress, 1),
            "operating_hour_overlap": round(c_overlap, 1),
            "event_occupancy_modifier": round(c_mod, 1),
            "building_sensitivity": arch["heat_sensitivity"],
        },
    }


def estimate_demand(req: AssetRequest, weather: WeatherSeries) -> dict:
    """Hourly demand estimate: base + occupancy + cooling + event loads."""
    arch = ARCHETYPES[req.building_type]
    occ_level = OCCUPANCY_FACTORS[req.occupancy_level]
    zone_mult = zone_internal_load_multiplier(req)

    base_load_mw = req.area_m2 * arch["base_load_kw_m2"] / 1000.0

    hours_iso: list[str] = []
    total: list[float] = []
    baseline_part: list[float] = []  # non-cooling demand
    cooling_part: list[float] = []

    for p in weather.points:
        hour = _hour_of(p.time)
        occ = occupancy_profile(hour, req) * occ_level

        occupancy_load_mw = req.area_m2 * arch["occupancy_load_kw_m2"] * occ / 1000.0

        # Event load: extra internal gains during an event afternoon/evening.
        event_load_mw = 0.0
        if req.event_day and 14 <= hour < 23:
            event_load_mw = 0.08 * base_load_mw + 0.03 * occupancy_load_mw

        cooling_degree = max(p.temp_c - BASE_TEMP_C, 0.0)
        cooling_degree_factor = min(cooling_degree / REFERENCE_COOLING_DEGREE, STRESS_TEMP_CAP)
        # Occupancy adds internal heat: cooling never drops below 55% of its
        # weather-driven value while the plant holds setpoint overnight.
        occupancy_factor = 0.55 + 0.45 * occ * zone_mult

        cooling_load_mw = (
            req.area_m2
            * arch["cooling_intensity_kw_m2"]
            * cooling_degree_factor
            * occupancy_factor
            / 1000.0
        )

        non_cooling = base_load_mw + occupancy_load_mw + event_load_mw
        hours_iso.append(p.time)
        baseline_part.append(round(non_cooling, 3))
        cooling_part.append(round(cooling_load_mw, 3))
        total.append(round(non_cooling + cooling_load_mw, 3))

    peak_idx = max(range(len(total)), key=lambda i: total[i])
    return {
        "hours": hours_iso,
        "total_mw": total,
        "baseline_mw": baseline_part,
        "cooling_mw": cooling_part,
        "peak_demand_mw": total[peak_idx],
        "peak_hour": hours_iso[peak_idx],
        "peak_index": peak_idx,
    }


def peak_cooling_window(demand: dict) -> PeakWindow:
    """Contiguous first-day window where demand is within 90% of peak."""
    total = demand["total_mw"][:24]
    if not total:
        return PeakWindow(start_hour=12, end_hour=17, description="default window")
    threshold = 0.9 * max(total)
    hot_hours = [
        _hour_of(demand["hours"][i]) for i in range(len(total)) if total[i] >= threshold
    ]
    start, end = min(hot_hours), max(hot_hours) + 1
    return PeakWindow(
        start_hour=start,
        end_hour=end,
        description=f"Estimated demand within 90% of peak between {start:02d}:00 and {end:02d}:00.",
    )


def scorch_scenario(req: AssetRequest, demand: dict, score: float) -> ScenarioSeries:
    """Baseline vs SCORCH-recommended demand profiles.

    SCORCH shifts (not eliminates) cooling: pre-cool in the hours before the
    demand peak, then modestly trim the computed peak window using the stored
    thermal mass. Peak reduction scales with risk; comfort-critical load is
    never cut hard.
    """
    category = risk_category(score)
    peak_cut = {"Low": 0.02, "Moderate": 0.05, "High": 0.08, "Very High": 0.10}[category]
    precool_boost = peak_cut * 0.7  # most of the shaved energy shifts earlier

    # Anchor the strategy to the demand-derived peak window, not fixed hours,
    # so the trim actually hits the hours that set the daily peak.
    window = peak_cooling_window(demand)
    trim_start, trim_end = window.start_hour, window.end_hour
    precool_start = max(6, trim_start - 4)

    baseline = list(demand["total_mw"])
    cooling = demand["cooling_mw"]
    scorch = []
    for i, mw in enumerate(baseline):
        hour = _hour_of(demand["hours"][i])
        adjusted = mw
        if precool_start <= hour < trim_start:   # pre-cool: charge thermal mass
            adjusted = mw + precool_boost * cooling[i]
        elif trim_start <= hour < trim_end:      # peak window: coast on thermal mass
            adjusted = mw - peak_cut * cooling[i]
        scorch.append(round(adjusted, 3))

    peak_base = max(baseline)
    peak_scorch = max(scorch)
    peak_reduction_mw = round(peak_base - peak_scorch, 3)
    peak_reduction_pct = round(100.0 * peak_reduction_mw / peak_base, 1) if peak_base else 0.0
    energy_change_pct = (
        round(100.0 * (sum(scorch) - sum(baseline)) / sum(baseline), 1) if sum(baseline) else 0.0
    )

    return ScenarioSeries(
        baseline_mw=baseline,
        scorch_mw=scorch,
        peak_reduction_mw=peak_reduction_mw,
        peak_reduction_pct=peak_reduction_pct,
        daily_energy_change_pct=energy_change_pct,
        note=(
            f"SCORCH scenario shifts cooling earlier (pre-cool {precool_start:02d}:00-"
            f"{trim_start:02d}:00) and trims the {trim_start:02d}:00-{trim_end:02d}:00 "
            f"peak window by ~{int(peak_cut * 100)}% of cooling load. "
            "These are screening estimates; comfort setpoints are assumed protected."
        ),
    )


def model_assumptions(req: AssetRequest, weather: WeatherSeries) -> list[str]:
    """Human-readable list of the assumptions behind an estimate."""
    arch = ARCHETYPES[req.building_type]
    return [
        f"Building archetype: {arch['label']} "
        f"(cooling intensity {arch['cooling_intensity_kw_m2']} kW/m2 at reference conditions, "
        f"base load {arch['base_load_kw_m2']} kW/m2).",
        f"Cooling balance point {BASE_TEMP_C} C; intensity saturates at "
        f"cooling-degree factor {STRESS_TEMP_CAP}.",
        f"Occupancy level '{req.occupancy_level}' -> factor "
        f"{OCCUPANCY_FACTORS[req.occupancy_level]}; simple open-hours occupancy ramp.",
        f"Weather source: {weather.source} ({'live' if weather.is_live else 'synthetic fallback'}).",
        "Zone internal-load factors are public archetype assumptions, not measured.",
        "No meter, BMS, or floor-plan data used (SCORCH Level 0).",
    ]


def confidence_level(weather: WeatherSeries) -> str:
    return (
        "medium (live public forecast, archetype building assumptions)"
        if weather.is_live
        else "low (synthetic weather fallback, archetype building assumptions)"
    )
