"""Tests for the SCORCH risk/demand model and API endpoints.

Network is never required: tests use the synthetic Kuwait hot-day weather
and (for endpoint tests) monkeypatch get_weather to stay offline.
"""

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import data_sources, main, risk_model  # noqa: E402
from app.data_sources import synthetic_kuwait_hot_day  # noqa: E402
from app.models import AssetRequest, OperatingHours  # noqa: E402


def mall_request(**overrides) -> AssetRequest:
    base = dict(
        latitude=29.2733,
        longitude=47.9770,
        building_type="mall",
        area_m2=130_000,
        operating_hours=OperatingHours(start_hour=10, end_hour=22),
    )
    base.update(overrides)
    return AssetRequest(**base)


# ---- synthetic weather --------------------------------------------------

def test_synthetic_weather_is_a_plausible_kuwait_hot_day():
    weather = synthetic_kuwait_hot_day()
    temps = [p.temp_c for p in weather.points]
    assert len(temps) == 48
    assert 44 <= max(temps) <= 52       # extreme afternoon
    assert 30 <= min(temps) <= 36       # warm night
    assert weather.is_live is False


# ---- risk score ---------------------------------------------------------

def test_risk_score_in_bounds_and_hot_day_is_high_risk():
    weather = synthetic_kuwait_hot_day()
    risk = risk_model.compute_heat_risk(mall_request(), weather)
    assert 0 <= risk["score"] <= 100
    assert risk["category"] in ("High", "Very High")
    assert risk["hours_above_45c"] > 0


def test_event_and_high_occupancy_raise_risk():
    weather = synthetic_kuwait_hot_day()
    quiet = risk_model.compute_heat_risk(mall_request(occupancy_level="low"), weather)
    busy = risk_model.compute_heat_risk(
        mall_request(event_day=True, occupancy_level="high"), weather
    )
    assert busy["score"] > quiet["score"]


def test_risk_categories_map_to_spec_bands():
    assert risk_model.risk_category(0) == "Low"
    assert risk_model.risk_category(30) == "Low"
    assert risk_model.risk_category(31) == "Moderate"
    assert risk_model.risk_category(55) == "Moderate"
    assert risk_model.risk_category(56) == "High"
    assert risk_model.risk_category(75) == "High"
    assert risk_model.risk_category(76) == "Very High"
    assert risk_model.risk_category(100) == "Very High"


# ---- demand model -------------------------------------------------------

def test_demand_estimate_is_positive_and_peaks_in_afternoon():
    weather = synthetic_kuwait_hot_day()
    demand = risk_model.estimate_demand(mall_request(), weather)
    assert all(mw > 0 for mw in demand["total_mw"])
    # Peak demand for a 130k m2 mall should be a plausible screening value.
    assert 10 <= demand["peak_demand_mw"] <= 60
    peak_hour = int(demand["peak_hour"][11:13])
    assert 11 <= peak_hour <= 19


def test_scorch_scenario_shifts_not_eliminates_load():
    weather = synthetic_kuwait_hot_day()
    req = mall_request()
    demand = risk_model.estimate_demand(req, weather)
    risk = risk_model.compute_heat_risk(req, weather)
    scenario = risk_model.scorch_scenario(req, demand, risk["score"])

    assert scenario.peak_reduction_mw > 0
    assert scenario.peak_reduction_pct < 20  # modest, not magical
    # Pre-cooling means morning demand goes UP somewhere.
    assert any(s > b for s, b in zip(scenario.scorch_mw, scenario.baseline_mw))
    # Energy roughly conserved: shifting, not deleting (within a few %).
    assert abs(scenario.daily_energy_change_pct) < 5


# ---- API endpoints (offline: monkeypatched weather) ---------------------

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        main, "get_weather", lambda lat, lon: synthetic_kuwait_hot_day()
    )
    monkeypatch.setattr(
        data_sources, "fetch_open_meteo",
        lambda lat, lon: (_ for _ in ()).throw(RuntimeError("offline test")),
    )
    return TestClient(main.app)


def test_root_lists_endpoints(client):
    body = client.get("/").json()
    assert body["name"].startswith("SCORCH")
    assert "POST /risk/heat" in body["endpoints"]


def test_example_asset(client):
    body = client.get("/assets/example/360-mall").json()
    assert body["asset"]["area_m2"] == 130_000
    assert len(body["asset"]["zones"]) == 7


def test_risk_endpoint(client):
    resp = client.post("/risk/heat", json=mall_request().model_dump())
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["heat_risk_score"] <= 100
    assert "public-data estimate" in body["disclaimer"]
    assert body["assumptions"]


def test_cooling_endpoint(client):
    resp = client.post("/cooling/estimate", json=mall_request().model_dump())
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["hourly_demand_mw"]) == 48
    assert body["peak_demand_mw"] > 0
    assert body["scorch_scenario"]["peak_reduction_mw"] >= 0


def test_actions_endpoint_very_high_risk(client):
    resp = client.post("/actions/recommend", json={
        "risk_score": 85, "building_type": "mall",
        "peak_window_start_hour": 12, "peak_window_end_hour": 17,
        "event_day": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_category"] == "Very High"
    assert "08:00" in body["pre_cooling_window"]
    assert body["what_not_to_do"]


def test_demo_endpoint(client):
    resp = client.get("/demo/360-mall")
    assert resp.status_code == 200
    body = resp.json()
    assert "executive_summary" in body
    assert body["risk"]["heat_risk_score"] > 0
    assert len(body["demand"]["hourly_demand_mw"]) == 48
    assert "public-data estimate" in body["executive_summary"]


def test_dashboard_served(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "SCORCH" in resp.text
