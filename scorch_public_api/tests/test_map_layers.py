"""Tests for the SCORCH map layer: GeoJSON shape + endpoint availability.

Fully offline: weather is forced to the synthetic generator and Overpass is
forced to fail, so the tests prove the fallback paths keep working.
"""

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import geo_sources, main, map_layers  # noqa: E402
from app.assets import EXAMPLE_ASSETS  # noqa: E402
from app.data_sources import synthetic_kuwait_hot_day  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    # Offline: synthetic weather everywhere, Overpass always fails.
    monkeypatch.setattr(map_layers, "get_weather", lambda lat, lon: synthetic_kuwait_hot_day())
    monkeypatch.setattr(main, "get_weather", lambda lat, lon: synthetic_kuwait_hot_day())
    monkeypatch.setattr(
        geo_sources, "fetch_overpass_buildings",
        lambda lat, lon, radius_m=500: (_ for _ in ()).throw(RuntimeError("offline test")),
    )
    return TestClient(main.app)


# ---- /map/assets ---------------------------------------------------------

def test_map_assets_is_valid_geojson(client):
    fc = client.get("/map/assets").json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == len(EXAMPLE_ASSETS) >= 5
    for f in fc["features"]:
        assert f["type"] == "Feature"
        assert f["geometry"]["type"] == "Point"
        lon, lat = f["geometry"]["coordinates"]  # GeoJSON order: [lon, lat]
        assert 46 < lon < 49 and 28 < lat < 31  # all in Kuwait
        p = f["properties"]
        for key in ("slug", "name", "building_type", "area_m2", "latitude",
                    "longitude", "operating_hours", "risk_score",
                    "risk_category", "disclaimer"):
            assert key in p
        assert p["risk_score"] is None  # no simulation has run for this layer
        assert "public-data estimate" in p["disclaimer"]


def test_map_single_asset_and_404(client):
    f = client.get("/map/assets/360-mall").json()
    assert f["type"] == "Feature"
    assert f["properties"]["slug"] == "360-mall"
    assert f["properties"]["area_m2"] == 130_000

    resp = client.get("/map/assets/no-such-asset")
    assert resp.status_code == 404
    assert "Unknown asset slug" in resp.json()["detail"]


# ---- /map/risk-layer -----------------------------------------------------

def test_risk_layer_scores_every_asset(client):
    fc = client.get("/map/risk-layer").json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == len(EXAMPLE_ASSETS)
    valid_colors = set(map_layers.RISK_COLORS.values())
    for f in fc["features"]:
        p = f["properties"]
        assert 0 <= p["risk_score"] <= 100
        assert p["risk_category"] in map_layers.RISK_COLORS
        assert p["marker_color"] == map_layers.RISK_COLORS[p["risk_category"]]
        assert p["marker_color"] in valid_colors
        assert "peak_window" in p and "executive_summary" in p
        assert "recommended_action_summary" in p
        assert p["confidence"] and p["assumptions"]
        assert "public-data estimate" in p["executive_summary"]


# ---- /map/buildings/nearby (Overpass forced to fail) ----------------------

def test_nearby_buildings_fallback_when_overpass_unavailable(client):
    a = EXAMPLE_ASSETS["360-mall"]
    fc = client.get(
        f"/map/buildings/nearby?lat={a['latitude']}&lon={a['longitude']}&radius_m=500"
    ).json()
    assert fc["type"] == "FeatureCollection"
    assert fc["properties"]["source"] == "fallback_public_assumption"
    assert fc["properties"]["is_live"] is False
    assert fc["properties"]["nearest_example_asset"] == "360-mall"
    assert "not a verified floor plan/BIM" in fc["properties"]["disclaimer"]

    types = sorted(f["geometry"]["type"] for f in fc["features"])
    assert types == ["Point", "Polygon"]
    for f in fc["features"]:
        assert f["properties"]["source"] == "fallback_public_assumption"


def test_nearby_buildings_generic_when_far_from_assets(client):
    fc = client.get("/map/buildings/nearby?lat=29.0&lon=48.5&radius_m=99999").json()
    assert fc["properties"]["nearest_example_asset"] is None
    assert fc["properties"]["source"] == "fallback_public_assumption"


# ---- fallback geometry unit checks ----------------------------------------

def test_fallback_footprint_polygon_is_closed_and_centered():
    feats = geo_sources.fallback_footprint(29.2733, 47.977, 130_000, "360 Mall")
    poly = next(f for f in feats if f["geometry"]["type"] == "Polygon")
    ring = poly["geometry"]["coordinates"][0]
    assert len(ring) == 5 and ring[0] == ring[-1]  # closed square ring
    lons = [c[0] for c in ring[:-1]]
    lats = [c[1] for c in ring[:-1]]
    assert min(lons) < 47.977 < max(lons)
    assert min(lats) < 29.2733 < max(lats)
    # Square side should approximate sqrt(area): ~360 m -> ~0.0032 deg lat.
    side_deg = max(lats) - min(lats)
    assert 0.002 < side_deg < 0.005
