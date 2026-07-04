"""Tests for the Grid-Aware Kuwait layer.

Fully offline: Open-Meteo and Overpass are forced to fail, proving the
fallback paths, and every grid endpoint must carry the MEWRE disclaimer.
"""

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import data_sources, grid_sources, main  # noqa: E402
from app.grid_assets import DISTRICTS, POWER_STATIONS  # noqa: E402
from app.models import GRID_DISCLAIMER  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    def _fail(*args, **kwargs):
        raise RuntimeError("offline test")

    monkeypatch.setattr(data_sources, "fetch_open_meteo", _fail)
    monkeypatch.setattr(grid_sources, "_overpass", _fail)
    return TestClient(main.app)


def test_grid_dashboard_loads(client):
    resp = client.get("/grid")
    assert resp.status_code == 200
    html = resp.text
    assert "Grid-Aware Kuwait" in html
    assert "not verified MEWRE" in html  # honesty strip on the page itself


def test_grid_assets_geojson(client):
    fc = client.get("/grid/assets").json()
    assert fc["type"] == "FeatureCollection"
    layers = {f["properties"]["layer"] for f in fc["features"]}
    assert {"power_station", "transmission_corridor",
            "example_building", "district_demand_cell"} <= layers
    assert fc["properties"]["disclaimer"] == GRID_DISCLAIMER


def test_power_stations_features(client):
    fc = client.get("/grid/power-stations").json()
    assert len(fc["features"]) == len(POWER_STATIONS) >= 7
    names = {f["properties"]["name"] for f in fc["features"]}
    assert any("Doha East" in n for n in names)
    assert any("Subiya" in n or "Sabiya" in n for n in names)
    for f in fc["features"]:
        p = f["properties"]
        assert p["fuel_type"] in ("natural_gas", "fuel_oil", "diesel", "mixed", "unknown")
        assert p["generation_type"] in (
            "combined_cycle", "open_cycle_gas_turbine", "steam", "unknown")
        assert p["capacity_mw"] is None or p["capacity_mw"] > 0
        assert p["confidence"] and p["assumptions"]
        assert p["disclaimer"] == GRID_DISCLAIMER
    # Uncertainty must be expressed somewhere, not invented away.
    assert any(f["properties"]["capacity_mw"] is None for f in fc["features"])


def test_demand_layer_positive_demand(client):
    fc = client.get("/grid/demand-layer").json()
    assert len(fc["features"]) == len(DISTRICTS)
    total = fc["properties"]["estimated_total_demand_mw"]
    assert total > 1000  # metro cells on a Kuwait summer day
    for f in fc["features"]:
        p = f["properties"]
        assert p["estimated_demand_mw"] > 0
        assert p["estimated_cooling_mw"] >= 0
        assert p["estimated_base_mw"] > 0
        assert p["peak_risk"] in ("Low", "Moderate", "High", "Very High")
    assert fc["properties"]["grid_stress"]["level"] in (
        "Normal", "Elevated", "High", "Critical")


def test_demand_layer_timeline_offsets(client):
    for off in ("0", "6", "24", "peak7d"):
        fc = client.get(f"/grid/demand-layer?hour_offset={off}").json()
        assert fc["properties"]["estimated_total_demand_mw"] > 0


def test_dispatch_simulate_positive_outputs(client):
    resp = client.post("/grid/dispatch-simulate", json={
        "total_estimated_load_mw": 12000,
        "reserve_margin_percent": 10,
        "generator_mix_scenario": "generic_kuwait_grid",
        "temperature_c": 48,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["estimated_generation_needed_mw"] > 12000  # includes losses
    fuel = body["estimated_fuel_burn_per_hour"]
    assert set(fuel) == {"natural_gas", "fuel_oil", "diesel"}
    assert all(v["mwh"] > 0 and v["energy_gj"] > 0 for v in fuel.values())
    assert body["estimated_emissions_per_hour"]["co2_tonnes"] > 0
    assert body["estimated_marginal_plant"]
    assert body["disclaimer"] == GRID_DISCLAIMER
    assert any("NOT actual MEWRE dispatch" in a for a in body["assumptions"])


def test_dispatch_scenarios_differ(client):
    def co2(scenario):
        return client.post("/grid/dispatch-simulate", json={
            "total_estimated_load_mw": 10000, "generator_mix_scenario": scenario,
        }).json()["estimated_emissions_per_hour"]["co2_tonnes"]

    assert co2("gas_priority") < co2("generic_kuwait_grid") < co2("oil_heavy_stress")


def test_grid_report_html(client):
    resp = client.get("/grid/report/kuwait")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text
    assert "Grid-Aware Kuwait" in html
    assert GRID_DISCLAIMER in html
    assert "Doha East" in html
    assert "Next data needed from MEWRE" in html


def test_osm_power_fallback_when_overpass_fails(client):
    fc = client.get("/grid/osm-power").json()
    assert fc["properties"]["source"] == "fallback_public_assumption"
    kinds = {f["properties"]["power"] for f in fc["features"]}
    assert {"plant", "line"} <= kinds
    assert all(f["properties"]["source"] == "fallback_public_assumption"
               for f in fc["features"])


def test_buildings_fallback_when_overpass_fails(client):
    fc = client.get("/buildings/footprints?bbox=29.30,47.95,29.35,48.00&limit=50").json()
    assert fc["properties"]["source"] == "fallback_public_assumption"
    assert len(fc["features"]) > 0
    for f in fc["features"]:
        assert f["properties"]["demand_class"] == "residential"
        assert f["geometry"]["type"] == "Polygon"


def test_no_grid_endpoint_claims_verified_mewre_data(client):
    """Every grid JSON endpoint must carry the disclaimer and never claim
    verified/actual real-time MEWRE telemetry."""
    json_endpoints = [
        ("GET", "/grid/assets"), ("GET", "/grid/power-stations"),
        ("GET", "/grid/osm-power"), ("GET", "/grid/demand-layer"),
        ("GET", "/grid/overview"),
        ("GET", "/buildings/footprints"),
    ]
    for method, url in json_endpoints:
        text = client.request(method, url).text
        assert "not verified MEWRE" in text, url
        assert "verified real-time MEWRE" not in text, url
    body = client.post("/grid/dispatch-simulate",
                       json={"total_estimated_load_mw": 5000}).text
    assert "not verified MEWRE" in body
