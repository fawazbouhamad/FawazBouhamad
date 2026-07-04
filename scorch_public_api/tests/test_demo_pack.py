"""Tests for Demo Pack v1: weekly outlook, fuel impact, HTML reports.

Fully offline: Open-Meteo is forced to fail so every weather call uses the
synthetic Kuwait fallback.
"""

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import data_sources, main  # noqa: E402
from app.assets import EXAMPLE_ASSETS  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    # Patch the fetch inside data_sources so EVERY get_weather() caller
    # (main, map_layers, outlook, reports) falls back to synthetic weather.
    def _fail(*args, **kwargs):
        raise RuntimeError("offline test")

    monkeypatch.setattr(data_sources, "fetch_open_meteo", _fail)
    return TestClient(main.app)


# ---- 7-day outlook --------------------------------------------------------

def test_weekly_outlook_returns_7_days(client):
    resp = client.get("/demo/360-mall/weekly")
    assert resp.status_code == 200
    body = resp.json()
    assert body["asset_slug"] == "360-mall"
    assert body["is_live"] is False  # synthetic fallback in tests
    assert len(body["days"]) == 7
    for day in body["days"]:
        assert len(day["date"]) == 10  # YYYY-MM-DD
        assert 0 <= day["heat_risk_score"] <= 100
        assert day["risk_category"] in ("Low", "Moderate", "High", "Very High")
        assert day["cooling_degree_hours"] > 0
        assert day["max_apparent_temp_c"] >= day["max_temp_c"]  # humidity proxy
        assert "pre-cool" in day["recommended_action_summary"].lower() or \
               "risk" in day["recommended_action_summary"]
    assert "public-data estimate" in body["disclaimer"]


def test_weekly_outlook_unknown_asset_404(client):
    assert client.get("/demo/not-a-real-asset/weekly").status_code == 404


# ---- grid/fuel impact -----------------------------------------------------

def test_fuel_impact_positive_reduction(client):
    resp = client.post("/grid/fuel-impact", json={
        "peak_reduction_mw": 2.5, "duration_hours": 5, "generator_type": "generic_grid",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["avoided_mwh"] == pytest.approx(12.5)
    assert body["avoided_mwh"] > 0
    assert body["estimated_emissions_avoided"]["co2_tonnes"] > 0
    assert body["estimated_fuel_avoided"]  # at least one fuel unit
    assert "public-data estimate" in body["disclaimer"]
    assert any("dispatch" in a for a in body["assumptions"])  # honesty note


def test_fuel_impact_all_generator_types(client):
    for gen in ("combined_cycle_gas", "simple_cycle_gas", "diesel_backup",
                "fuel_oil_steam", "generic_grid"):
        body = client.post("/grid/fuel-impact", json={
            "peak_reduction_mw": 1.0, "duration_hours": 1, "generator_type": gen,
        }).json()
        assert body["avoided_mwh"] == 1.0
        assert body["estimated_emissions_avoided"]["co2_tonnes"] > 0


def test_fuel_impact_rejects_bad_input(client):
    assert client.post("/grid/fuel-impact", json={
        "peak_reduction_mw": 1.0, "duration_hours": 5, "generator_type": "cold_fusion",
    }).status_code == 422
    assert client.post("/grid/fuel-impact", json={
        "peak_reduction_mw": -1.0, "duration_hours": 5,
    }).status_code == 422


# ---- HTML reports ---------------------------------------------------------

def test_asset_report_returns_html(client):
    resp = client.get("/report/360-mall")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text
    assert "SCORCH Heat Risk Report" in html
    assert "360 Mall" in html
    assert "public-data estimate" in html
    assert "7-day outlook" in html
    assert "What private data would improve accuracy" in html


def test_asset_report_unknown_slug_404(client):
    assert client.get("/report/not-a-real-asset").status_code == 404


def test_portfolio_report_returns_html_with_all_assets(client):
    resp = client.get("/report/portfolio/kuwait")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text
    assert "Portfolio" in html
    for asset in EXAMPLE_ASSETS.values():
        assert asset["name"] in html
    assert "public-data estimate" in html


# ---- regressions ----------------------------------------------------------

def test_dashboard_still_loads_with_new_controls(client):
    html = client.get("/dashboard").text
    assert "Run SCORCH simulation" in html
    assert "Run 7-day outlook" in html
    assert "portfolio report" in html.lower()


def test_root_lists_demo_pack_endpoints(client):
    endpoints = client.get("/").json()["endpoints"]
    assert "GET /demo/{asset_slug}/weekly" in endpoints
    assert "POST /grid/fuel-impact" in endpoints
    assert "GET /report/{asset_slug}" in endpoints
