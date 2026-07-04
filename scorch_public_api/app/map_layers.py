"""GeoJSON builders for the SCORCH map layer.

Turns the built-in example assets into GeoJSON FeatureCollections, and runs
the lightweight Level-0 risk pipeline per asset for the risk layer. All
outputs carry the public-data disclaimer.
"""

from __future__ import annotations

from fastapi import HTTPException

from . import risk_model
from .assets import EXAMPLE_ASSETS
from .data_sources import get_weather
from .models import ActionRequest, AssetRequest, PUBLIC_DATA_DISCLAIMER
from .recommendations import build_action_plan

# Risk category -> marker color (spec: green / yellow / orange / red).
RISK_COLORS = {
    "Low": "#2e7d32",
    "Moderate": "#f9a825",
    "High": "#ef6c00",
    "Very High": "#c62828",
}
UNKNOWN_COLOR = "#8d8d8d"  # asset shown before any simulation has run


def asset_to_request(asset: dict) -> AssetRequest:
    return AssetRequest(
        latitude=asset["latitude"],
        longitude=asset["longitude"],
        building_type=asset["building_type"],
        area_m2=asset["area_m2"],
        operating_hours=asset["operating_hours"],
        zones=asset.get("zones"),
    )


def _base_properties(slug: str, asset: dict) -> dict:
    return {
        "slug": slug,
        "name": asset["name"],
        "building_type": asset["building_type"],
        "area_m2": asset["area_m2"],
        "latitude": asset["latitude"],
        "longitude": asset["longitude"],
        "operating_hours": asset["operating_hours"],
        "disclaimer": PUBLIC_DATA_DISCLAIMER,
    }


def asset_feature(slug: str, asset: dict, extra: dict | None = None) -> dict:
    props = _base_properties(slug, asset)
    # /map/assets promises these keys even before a simulation has run.
    props.setdefault("risk_score", None)
    props.setdefault("risk_category", None)
    if extra:
        props.update(extra)
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [asset["longitude"], asset["latitude"]],
        },
        "properties": props,
    }


def assets_feature_collection() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [asset_feature(slug, a) for slug, a in EXAMPLE_ASSETS.items()],
        "properties": {"disclaimer": PUBLIC_DATA_DISCLAIMER},
    }


def get_asset_or_404(slug: str) -> dict:
    asset = EXAMPLE_ASSETS.get(slug)
    if asset is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown asset slug '{slug}'. Known: {sorted(EXAMPLE_ASSETS)}",
        )
    return asset


def risk_feature_collection() -> dict:
    """Run the lightweight SCORCH pipeline for every built-in asset."""
    features = []
    for slug, asset in EXAMPLE_ASSETS.items():
        req = asset_to_request(asset)
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
            )
        )
        summary = (
            f"{asset['name']}: heat risk {risk['score']}/100 ({risk['category']}). "
            f"Max forecast temperature {risk['max_temp_c']:.1f} C, estimated peak demand "
            f"{demand['peak_demand_mw']:.1f} MW. Protect "
            f"{window.start_hour:02d}:00-{window.end_hour:02d}:00. {PUBLIC_DATA_DISCLAIMER}"
        )
        features.append(
            asset_feature(
                slug,
                asset,
                extra={
                    "risk_score": risk["score"],
                    "risk_category": risk["category"],
                    "marker_color": RISK_COLORS[risk["category"]],
                    "peak_window": window.model_dump(),
                    "peak_demand_mw": demand["peak_demand_mw"],
                    "peak_reduction_mw": scenario.peak_reduction_mw,
                    "peak_reduction_pct": scenario.peak_reduction_pct,
                    "executive_summary": summary,
                    "recommended_action_summary": (
                        f"Pre-cool {plan.pre_cooling_window}; "
                        f"{plan.peak_protection_window}"
                    ),
                    "confidence": risk_model.confidence_level(weather),
                    "assumptions": risk_model.model_assumptions(req, weather),
                },
            )
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "disclaimer": PUBLIC_DATA_DISCLAIMER,
            "risk_colors": RISK_COLORS,
        },
    }
