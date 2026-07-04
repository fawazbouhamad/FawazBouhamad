"""SCORCH Public Climate Risk API — FastAPI application.

Run locally:
    uvicorn app.main:app --reload
Dashboard:   http://127.0.0.1:8000/dashboard
API docs:    http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from . import map_layers, risk_model
from .assets import EXAMPLE_ASSETS, MALL_360
from .data_sources import get_weather
from .geo_sources import nearby_buildings
from .models import (
    ActionPlan,
    ActionRequest,
    AssetRequest,
    CoolingEstimateResponse,
    HeatRiskResponse,
    PUBLIC_DATA_DISCLAIMER,
)
from .recommendations import build_action_plan

API_VERSION = "0.2.0"
DASHBOARD_FILE = Path(__file__).resolve().parent.parent / "dashboard" / "index.html"

app = FastAPI(
    title="SCORCH Public Climate Risk API",
    version=API_VERSION,
    description=(
        "Public-data heat-driven cooling risk screening for Kuwait/GCC buildings. "
        + PUBLIC_DATA_DISCLAIMER
    ),
)


def _mall_360_request(**overrides) -> AssetRequest:
    """Build an AssetRequest from the 360 Mall public profile."""
    base = {
        "latitude": MALL_360["latitude"],
        "longitude": MALL_360["longitude"],
        "building_type": MALL_360["building_type"],
        "area_m2": MALL_360["area_m2"],
        "operating_hours": MALL_360["operating_hours"],
        "zones": MALL_360["zones"],
    }
    base.update(overrides)
    return AssetRequest(**base)


@app.get("/")
def root() -> dict:
    return {
        "name": "SCORCH Public Climate Risk API",
        "version": API_VERSION,
        "disclaimer": PUBLIC_DATA_DISCLAIMER,
        "endpoints": {
            "GET /": "this index",
            "GET /assets/example/360-mall": "example public asset profile",
            "POST /risk/heat": "heat risk score from public weather",
            "POST /cooling/estimate": "hourly demand + SCORCH scenario estimate",
            "POST /actions/recommend": "operational action plan for a risk score",
            "GET /demo/360-mall": "full demo run for 360 Mall",
            "GET /map/assets": "built-in example assets as GeoJSON",
            "GET /map/assets/{asset_slug}": "one example asset as GeoJSON",
            "GET /map/risk-layer": "risk-scored GeoJSON layer for all example assets",
            "GET /map/buildings/nearby": "OSM footprints near a point (fallback geometry if offline)",
            "GET /dashboard": "interactive dashboard with map",
            "GET /docs": "OpenAPI docs",
        },
    }


@app.get("/assets/example/360-mall")
def example_asset() -> dict:
    return {"disclaimer": PUBLIC_DATA_DISCLAIMER, "asset": MALL_360}


def _run_risk(req: AssetRequest) -> HeatRiskResponse:
    weather = get_weather(req.latitude, req.longitude)
    risk = risk_model.compute_heat_risk(req, weather)
    demand = risk_model.estimate_demand(req, weather)
    return HeatRiskResponse(
        weather=weather,
        hourly_temperature_c=[p.temp_c for p in weather.points],
        cooling_degree_hours=risk["cooling_degree_hours"],
        hours_above_45c=risk["hours_above_45c"],
        max_temp_c=risk["max_temp_c"],
        heat_risk_score=risk["score"],
        risk_category=risk["category"],
        peak_cooling_window=risk_model.peak_cooling_window(demand),
        confidence=risk_model.confidence_level(weather),
        assumptions=risk_model.model_assumptions(req, weather)
        + [f"Risk score components: {risk['components']}"],
    )


@app.post("/risk/heat")
def heat_risk(req: AssetRequest) -> HeatRiskResponse:
    return _run_risk(req)


def _run_cooling(req: AssetRequest) -> CoolingEstimateResponse:
    weather = get_weather(req.latitude, req.longitude)
    risk = risk_model.compute_heat_risk(req, weather)
    demand = risk_model.estimate_demand(req, weather)
    scenario = risk_model.scorch_scenario(req, demand, risk["score"])
    return CoolingEstimateResponse(
        weather=weather,
        hours=demand["hours"],
        hourly_demand_mw=demand["total_mw"],
        baseline_demand_mw=demand["baseline_mw"],
        cooling_demand_mw=demand["cooling_mw"],
        peak_demand_mw=demand["peak_demand_mw"],
        peak_hour=demand["peak_hour"],
        risk_category=risk["category"],
        scorch_scenario=scenario,
        confidence=risk_model.confidence_level(weather),
        assumptions=risk_model.model_assumptions(req, weather),
    )


@app.post("/cooling/estimate")
def cooling_estimate(req: AssetRequest) -> CoolingEstimateResponse:
    return _run_cooling(req)


@app.post("/actions/recommend")
def actions_recommend(req: ActionRequest) -> ActionPlan:
    return build_action_plan(req)


@app.get("/demo/360-mall")
def demo_360_mall(event_day: bool = False, occupancy_level: str = "medium") -> dict:
    """Full pipeline for the 360 Mall example asset."""
    if occupancy_level not in ("low", "medium", "high"):
        occupancy_level = "medium"
    req = _mall_360_request(event_day=event_day, occupancy_level=occupancy_level)

    weather = get_weather(req.latitude, req.longitude)
    risk = risk_model.compute_heat_risk(req, weather)
    demand = risk_model.estimate_demand(req, weather)
    scenario = risk_model.scorch_scenario(req, demand, risk["score"])
    window = risk_model.peak_cooling_window(demand)
    plan = build_action_plan(
        ActionRequest(
            risk_score=risk["score"],
            building_type=req.building_type,
            peak_window_start_hour=window.start_hour,
            peak_window_end_hour=min(window.end_hour, 24),
            event_day=req.event_day,
        )
    )

    summary = (
        f"SCORCH screening for 360 Mall (public assumptions, ~{int(req.area_m2):,} m2): "
        f"heat risk is {risk['score']}/100 ({risk['category']}). "
        f"Peak outdoor temperature is forecast at {risk['max_temp_c']:.1f} C with "
        f"{risk['hours_above_45c']} hour(s) above 45 C over the next 48h. "
        f"Estimated peak demand is {demand['peak_demand_mw']:.1f} MW around {demand['peak_hour']}. "
        f"Recommended play: pre-cool {plan.pre_cooling_window.split(' (')[0]}, then protect the "
        f"{window.start_hour:02d}:00-{window.end_hour:02d}:00 window. Following the SCORCH plan is "
        f"estimated to cut the peak by ~{scenario.peak_reduction_mw:.1f} MW "
        f"({scenario.peak_reduction_pct}%) with a {scenario.daily_energy_change_pct:+.1f}% daily "
        f"energy change. {PUBLIC_DATA_DISCLAIMER}"
    )

    return {
        "disclaimer": PUBLIC_DATA_DISCLAIMER,
        "asset": MALL_360,
        "weather": weather.model_dump(),
        "risk": {
            "heat_risk_score": risk["score"],
            "risk_category": risk["category"],
            "max_temp_c": risk["max_temp_c"],
            "cooling_degree_hours": risk["cooling_degree_hours"],
            "hours_above_45c": risk["hours_above_45c"],
            "components": risk["components"],
        },
        "peak_cooling_window": window.model_dump(),
        "demand": {
            "hours": demand["hours"],
            "hourly_demand_mw": demand["total_mw"],
            "baseline_demand_mw": demand["baseline_mw"],
            "cooling_demand_mw": demand["cooling_mw"],
            "peak_demand_mw": demand["peak_demand_mw"],
            "peak_hour": demand["peak_hour"],
        },
        "scorch_scenario": scenario.model_dump(),
        "recommendations": plan.model_dump(),
        "confidence": risk_model.confidence_level(weather),
        "assumptions": risk_model.model_assumptions(req, weather),
        "executive_summary": summary,
    }


@app.get("/map/assets")
def map_assets() -> dict:
    """All built-in example assets as a GeoJSON FeatureCollection."""
    return map_layers.assets_feature_collection()


@app.get("/map/assets/{asset_slug}")
def map_asset(asset_slug: str) -> dict:
    """One built-in example asset as a GeoJSON Feature (404 if unknown)."""
    asset = map_layers.get_asset_or_404(asset_slug)
    return map_layers.asset_feature(asset_slug, asset)


@app.get("/map/risk-layer")
def map_risk_layer() -> dict:
    """Lightweight SCORCH risk simulation for every built-in asset, as GeoJSON."""
    return map_layers.risk_feature_collection()


@app.get("/map/buildings/nearby")
def map_buildings_nearby(lat: float, lon: float, radius_m: int = 500) -> dict:
    """OSM building footprints near a point via Overpass (optional, free).

    Falls back to public-assumption geometry (asset point + approximate
    square buffer) whenever Overpass is unreachable or empty, so the map
    keeps working offline. radius_m is clamped to 100-1500 m to stay a
    polite Overpass citizen.
    """
    radius_m = max(100, min(radius_m, 1500))
    # Use the nearest example asset (if reasonably close) to label/size the
    # fallback geometry; otherwise use a generic buffer.
    nearest_slug, nearest_asset, best = None, None, float("inf")
    for slug, asset in EXAMPLE_ASSETS.items():
        d2 = (asset["latitude"] - lat) ** 2 + (asset["longitude"] - lon) ** 2
        if d2 < best:
            nearest_slug, nearest_asset, best = slug, asset, d2
    if nearest_asset is not None and best < (0.03**2):  # within ~3 km
        name, area = nearest_asset["name"], nearest_asset["area_m2"]
    else:
        nearest_slug, name, area = None, "Unnamed location (generic buffer)", 20_000.0
    result = nearby_buildings(lat, lon, radius_m, area, name)
    result["properties"]["nearest_example_asset"] = nearest_slug
    return result


@app.get("/dashboard")
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_FILE, media_type="text/html")
