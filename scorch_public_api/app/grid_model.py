"""SCORCH grid model: district demand, grid stress, dispatch/fuel simulation.

Everything here is a transparent screening model on public assumptions:
  district_demand = base_mw * activity_factor + cooling_mw_per_c
                    * cooling_degree * (0.7 + 0.3 * activity_factor)
It never reads or claims MEWRE meter, SCADA, dispatch, or fuel telemetry.
"""

from __future__ import annotations

from datetime import datetime

from .data_sources import get_weather
from .grid_assets import (
    DISTRICT_ASSUMPTIONS,
    DISTRICTS,
    INSTALLED_CAPACITY_MW,
    district_polygon,
)
from .models import DispatchRequest, DispatchResponse, GRID_DISCLAIMER, WeatherSeries
from .risk_model import BASE_TEMP_C

KUWAIT_CENTER = (29.35, 47.95)  # weather reference point for the grid layer
GRID_LOSSES = 0.08              # assumed transmission/distribution losses
HEAT_DERATE_PER_C = 0.004       # capacity derate per degree above 35 C
# Assumed share of national load covered by the modelled district cells.
# Used to scale cell totals to a national-scale estimate for the stress ratio.
COVERAGE_FACTOR = 0.70

# Fuel-mix scenarios: generation share by fuel. Approximate, transparent.
MIX_SCENARIOS: dict[str, dict] = {
    "generic_kuwait_grid": {
        "shares": {"natural_gas": 0.60, "fuel_oil": 0.30, "diesel": 0.10},
        "marginal": "open-cycle gas turbine (gas/gasoil peaker)",
    },
    "gas_priority": {
        "shares": {"natural_gas": 0.85, "fuel_oil": 0.10, "diesel": 0.05},
        "marginal": "combined-cycle gas turbine",
    },
    "diesel_backup_stress": {
        "shares": {"natural_gas": 0.50, "fuel_oil": 0.25, "diesel": 0.25},
        "marginal": "distributed diesel backup generators",
    },
    "oil_heavy_stress": {
        "shares": {"natural_gas": 0.35, "fuel_oil": 0.55, "diesel": 0.10},
        "marginal": "heavy-fuel-oil steam unit",
    },
}

# Per-MWh fuel factors (typical heat rates + standard emission factors).
FUEL_FACTORS = {
    "natural_gas": {"gj": 7.8, "m3": 205.0, "co2_t": 0.45},
    "fuel_oil": {"gj": 10.5, "litres": 260.0, "co2_t": 0.82},
    "diesel": {"gj": 10.0, "litres": 265.0, "co2_t": 0.72},
}

STRESS_LEVELS = [  # (max ratio, label, color)
    (0.75, "Normal", "#2e7d32"),
    (0.85, "Elevated", "#f9a825"),
    (0.95, "High", "#ef6c00"),
    (99.0, "Critical", "#c62828"),
]


def activity_factor(hour: int, is_weekend: bool) -> float:
    """0.8-1.15 time-of-day activity profile (assumption)."""
    if hour < 6:
        base = 0.80
    elif hour < 10:
        base = 0.90 + 0.02 * (hour - 6)
    elif hour < 17:
        base = 1.00
    elif hour < 22:
        base = 1.10  # Kuwait evening peak (assumption)
    else:
        base = 0.95
    return round(base * (0.95 if is_weekend else 1.0), 3)


def pick_weather_point(weather: WeatherSeries, hour_offset: int | str = 0):
    """Pick the forecast point 'now + offset hours' (or the 7-day peak)."""
    now_hour = datetime.now().hour
    if hour_offset == "peak7d":
        idx = max(range(len(weather.points)), key=lambda i: weather.points[i].temp_c)
        return weather.points[idx], "7-day peak"
    idx = min(now_hour + int(hour_offset), len(weather.points) - 1)
    label = "now" if hour_offset == 0 else f"+{hour_offset}h"
    return weather.points[idx], label


def grid_stress(total_demand_mw: float, temp_c: float) -> dict:
    derate = 1.0 - HEAT_DERATE_PER_C * max(temp_c - 35.0, 0.0)
    available = INSTALLED_CAPACITY_MW * derate
    ratio = total_demand_mw * (1 + GRID_LOSSES) / available if available else 9.9
    for upper, label, color in STRESS_LEVELS:
        if ratio <= upper:
            return {
                "estimated_available_capacity_mw": round(available, 0),
                "demand_to_capacity_ratio": round(ratio, 3),
                "level": label,
                "color": color,
                "note": (
                    f"Assumed installed capacity {INSTALLED_CAPACITY_MW:,.0f} MW "
                    f"derated {100 * (1 - derate):.1f}% for heat; +{GRID_LOSSES:.0%} losses."
                ),
            }
    raise AssertionError("unreachable")


def district_demand(d: dict, temp_c: float, hour: int, is_weekend: bool) -> dict:
    act = activity_factor(hour, is_weekend)
    cooling_degree = max(temp_c - BASE_TEMP_C, 0.0)
    base = d["base_mw"] * act
    cooling = d["cooling_mw_per_c"] * cooling_degree * (0.7 + 0.3 * act)
    total = base + cooling
    # Peak-risk category by how cooling-dominated and hot the cell is.
    if temp_c >= 47:
        risk = "Very High"
    elif temp_c >= 44:
        risk = "High"
    elif temp_c >= 38:
        risk = "Moderate"
    else:
        risk = "Low"
    return {
        "estimated_demand_mw": round(total, 1),
        "estimated_base_mw": round(base, 1),
        "estimated_cooling_mw": round(cooling, 1),
        "cooling_share": round(cooling / total, 2) if total else 0.0,
        "peak_risk": risk,
        "activity_factor": act,
    }


def demand_layer(hour_offset: int | str = 0) -> dict:
    """GeoJSON FeatureCollection of district cells with demand estimates."""
    weather = get_weather(*KUWAIT_CENTER, days=7)
    point, when = pick_weather_point(weather, hour_offset)
    ts = datetime.fromisoformat(point.time)
    is_weekend = ts.weekday() in (4, 5)  # Fri/Sat

    features, total, cooling = [], 0.0, 0.0  # metro-cell sums
    for d in DISTRICTS:
        est = district_demand(d, point.temp_c, ts.hour, is_weekend)
        total += est["estimated_demand_mw"]
        cooling += est["estimated_cooling_mw"]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [district_polygon(d)]},
            "properties": {
                "slug": d["slug"], "name": d["name"],
                "dominant_types": d["dominant_types"],
                "temperature_c": point.temp_c,
                "apparent_temperature_c": point.apparent_temp_c,
                **est,
                "disclaimer": GRID_DISCLAIMER,
            },
        })

    national = total / COVERAGE_FACTOR  # scale cells to a national-scale estimate
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "disclaimer": GRID_DISCLAIMER,
            "when": when,
            "timestamp": point.time,
            "temperature_c": point.temp_c,
            "apparent_temperature_c": point.apparent_temp_c,
            "weather_source": weather.source,
            "is_live_weather": weather.is_live,
            "estimated_total_demand_mw": round(total, 0),
            "estimated_cooling_demand_mw": round(cooling, 0),
            "estimated_national_demand_mw": round(national, 0),
            "grid_stress": grid_stress(national, point.temp_c),
            "assumptions": DISTRICT_ASSUMPTIONS
            + [f"Cells assumed to cover ~{COVERAGE_FACTOR:.0%} of national load; "
               "stress ratio uses the scaled national estimate."],
            "confidence": "low (synthetic/assumed parameters)" if not weather.is_live
            else "low-medium (live public weather, assumed parameters)",
        },
    }


def dispatch_simulate(req: DispatchRequest) -> DispatchResponse:
    scenario = MIX_SCENARIOS[req.generator_mix_scenario]
    generation = req.total_estimated_load_mw * (1 + GRID_LOSSES)
    stress = grid_stress(req.total_estimated_load_mw, req.temperature_c)
    available = stress["estimated_available_capacity_mw"]
    reserve = available - generation
    target_reserve = generation * req.reserve_margin_percent / 100.0
    reserve_status = (
        "adequate" if reserve >= target_reserve
        else "below target" if reserve > 0
        else "deficit (load shedding risk in this scenario)"
    )

    fuel_burn: dict[str, dict[str, float]] = {}
    emissions_t = 0.0
    for fuel, share in scenario["shares"].items():
        mwh = generation * share  # one hour at this load
        f = FUEL_FACTORS[fuel]
        entry = {"mwh": round(mwh, 1), "energy_gj": round(mwh * f["gj"], 0)}
        if "m3" in f:
            entry["volume_m3"] = round(mwh * f["m3"], 0)
        if "litres" in f:
            entry["volume_litres"] = round(mwh * f["litres"], 0)
        fuel_burn[fuel] = entry
        emissions_t += mwh * f["co2_t"]

    return DispatchResponse(
        scenario=req.generator_mix_scenario,
        estimated_generation_needed_mw=round(generation, 0),
        estimated_available_capacity_mw=available,
        estimated_reserve_mw=round(reserve, 0),
        reserve_status=reserve_status,
        estimated_fuel_burn_per_hour=fuel_burn,
        estimated_emissions_per_hour={"co2_tonnes": round(emissions_t, 0)},
        estimated_marginal_plant=scenario["marginal"],
        grid_stress=stress,
        confidence="low (screening merit-order shares, typical heat rates)",
        assumptions=[
            f"Generation = load x (1 + {GRID_LOSSES:.0%} assumed losses), for one hour.",
            f"Fuel shares ({req.generator_mix_scenario}): {scenario['shares']} — "
            "assumed scenario, NOT actual MEWRE dispatch.",
            "Typical heat rates and standard emission factors per fuel.",
            f"Capacity derated {HEAT_DERATE_PER_C:.1%}/C above 35 C "
            f"(at {req.temperature_c} C).",
        ],
    )


def climate_grid_overview(hour_offset: int | str = 0,
                          scenario: str = "generic_kuwait_grid") -> dict:
    """KPIs coupling climate -> demand -> stress -> fuel, for the dashboard."""
    layer = demand_layer(hour_offset)
    props = layer["properties"]
    total = props["estimated_total_demand_mw"]
    cooling = props["estimated_cooling_demand_mw"]
    national = props["estimated_national_demand_mw"]
    temp = props["temperature_c"]

    if scenario not in MIX_SCENARIOS:
        scenario = "generic_kuwait_grid"
    # Dispatch/fuel are simulated at the national-scale estimate.
    dispatch = dispatch_simulate(DispatchRequest(
        total_estimated_load_mw=max(min(national, 30_000.0), 1.0),
        generator_mix_scenario=scenario,
        temperature_c=temp,
        apparent_temperature_c=props["apparent_temperature_c"],
    ))

    # Climate coupling: demand/fuel at current temp vs a 35 C reference day.
    ref = sum(
        district_demand(d, 35.0, datetime.fromisoformat(props["timestamp"]).hour,
                        False)["estimated_cooling_mw"]
        for d in DISTRICTS
    )
    added_cooling = max(cooling - ref, 0.0)
    shares = MIX_SCENARIOS[scenario]["shares"]
    added_gas_gj = added_cooling * (1 + GRID_LOSSES) * shares["natural_gas"] * FUEL_FACTORS["natural_gas"]["gj"]
    added_co2 = added_cooling * (1 + GRID_LOSSES) * sum(
        s * FUEL_FACTORS[f]["co2_t"] for f, s in shares.items()
    )

    ranked = sorted(layer["features"], key=lambda f: f["properties"]["estimated_cooling_mw"],
                    reverse=True)
    top = ranked[0]["properties"]

    return {
        "disclaimer": GRID_DISCLAIMER,
        "when": props["when"],
        "timestamp": props["timestamp"],
        "weather_source": props["weather_source"],
        "is_live_weather": props["is_live_weather"],
        "temperature_c": temp,
        "apparent_temperature_c": props["apparent_temperature_c"],
        "estimated_total_demand_mw": total,
        "estimated_cooling_demand_mw": cooling,
        "estimated_national_demand_mw": national,
        "grid_stress": props["grid_stress"],
        "dispatch": dispatch.model_dump(),
        "climate_impact": {
            "added_cooling_mw_vs_35c": round(added_cooling, 0),
            "added_gas_burn_gj_per_hour": round(added_gas_gj, 0),
            "added_co2_tonnes_per_hour": round(added_co2, 0),
            "most_stressed_district": top["name"],
            "most_stressed_building_types": top["dominant_types"],
            "note": "Added values compare current temperature vs a 35 C reference.",
        },
        "confidence": props["confidence"],
        "assumptions": DISTRICT_ASSUMPTIONS,
    }
