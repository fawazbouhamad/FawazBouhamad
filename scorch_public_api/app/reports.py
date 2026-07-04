"""Printable HTML reports for the SCORCH Demo Pack.

Plain f-string templates — no template engine, no frontend framework.
Reports use a light theme so they print cleanly from the browser
(Ctrl/Cmd+P). Every page carries the public-data disclaimer.
"""

from __future__ import annotations

from . import grid_model, risk_model
from .assets import EXAMPLE_ASSETS
from .data_sources import get_weather
from .grid_assets import POWER_STATIONS
from .grid_impact import compute_fuel_impact
from .map_layers import RISK_COLORS, asset_to_request, get_asset_or_404
from .models import (
    ActionRequest,
    DispatchRequest,
    FuelImpactRequest,
    GRID_DISCLAIMER,
    PUBLIC_DATA_DISCLAIMER,
    DATA_UPGRADES,
)
from .outlook import build_weekly_outlook
from .recommendations import build_action_plan

_CSS = """
  * { box-sizing: border-box; }
  body { margin: 0; font-family: Georgia, 'Times New Roman', serif; color: #1c1917;
         background: #faf7f2; line-height: 1.5; }
  .page { max-width: 880px; margin: 0 auto; padding: 32px 28px 48px; }
  header.rpt { border-bottom: 3px solid #c2410c; padding-bottom: 12px; margin-bottom: 20px; }
  header.rpt h1 { margin: 0; font-size: 26px; }
  header.rpt .sub { color: #57534e; font-size: 14px; margin-top: 4px; }
  .disclaimer { background: #fff7ed; border-left: 4px solid #c2410c; padding: 10px 14px;
                font-size: 13px; margin: 16px 0; }
  h2 { font-size: 17px; margin: 26px 0 8px; border-bottom: 1px solid #e7e5e4; padding-bottom: 4px; }
  .cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0; }
  .card { flex: 1 1 160px; background: #fff; border: 1px solid #e7e5e4; border-radius: 8px;
          padding: 12px 14px; }
  .card .k { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #78716c; }
  .card .v { font-size: 22px; font-weight: 700; margin-top: 2px; font-family: system-ui, sans-serif; }
  .card .s { font-size: 12px; color: #78716c; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; background: #fff; }
  th, td { border: 1px solid #e7e5e4; padding: 6px 9px; text-align: left; }
  th { background: #f5f5f4; font-family: system-ui, sans-serif; font-size: 12px; }
  .chip { display: inline-block; padding: 1px 10px; border-radius: 10px; color: #fff;
          font-size: 11.5px; font-weight: 700; font-family: system-ui, sans-serif; }
  ul { margin: 6px 0; padding-left: 22px; font-size: 13.5px; }
  .muted { color: #78716c; font-size: 12.5px; }
  a.btn { display: inline-block; background: #c2410c; color: #fff; padding: 7px 14px;
          border-radius: 6px; text-decoration: none; font-family: system-ui, sans-serif;
          font-size: 13px; margin: 4px 8px 4px 0; }
  footer.rpt { margin-top: 32px; border-top: 1px solid #e7e5e4; padding-top: 10px;
               font-size: 12px; color: #78716c; }
  @media print { .no-print { display: none; } body { background: #fff; }
                 .card, table { break-inside: avoid; } }
"""


def _chip(category: str) -> str:
    color = RISK_COLORS.get(category, "#8d8d8d")
    return f'<span class="chip" style="background:{color}">{category}</span>'


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{_CSS}</style></head>
<body><div class="page">{body}
<footer class="rpt">SCORCH Public Climate Risk API — Level 0 (public data only).
{PUBLIC_DATA_DISCLAIMER} Weather: Open-Meteo (free) or synthetic fallback.
Geodata: OpenStreetMap contributors (ODbL). No Google Maps/Earth data is used.</footer>
</div></body></html>"""


def _run_asset_pipeline(slug: str) -> dict:
    """Weather -> risk -> demand -> scenario -> plan for one asset (48h)."""
    asset = get_asset_or_404(slug)
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
    return dict(asset=asset, req=req, weather=weather, risk=risk, demand=demand,
                scenario=scenario, window=window, plan=plan)


def asset_report_html(slug: str) -> str:
    r = _run_asset_pipeline(slug)
    asset, risk, demand, scenario, window, plan = (
        r["asset"], r["risk"], r["demand"], r["scenario"], r["window"], r["plan"]
    )
    weekly = build_weekly_outlook(slug)
    duration = max(window.end_hour - window.start_hour, 1)
    fuel = compute_fuel_impact(FuelImpactRequest(
        peak_reduction_mw=max(scenario.peak_reduction_mw, 0.0),
        duration_hours=duration,
        generator_type="generic_grid",
    ))
    lat, lon = asset["latitude"], asset["longitude"]
    oh = asset["operating_hours"]

    weekly_rows = "".join(
        f"<tr><td>{d.date}</td><td>{d.max_temp_c:.1f}</td>"
        f"<td>{'' if d.max_apparent_temp_c is None else f'{d.max_apparent_temp_c:.1f}'}</td>"
        f"<td>{d.cooling_degree_hours:.0f}</td>"
        f"<td>{d.heat_risk_score:.0f} {_chip(d.risk_category)}</td>"
        f"<td>{d.peak_cooling_window.start_hour:02d}:00–{d.peak_cooling_window.end_hour:02d}:00</td>"
        f"<td>{d.recommended_action_summary}</td></tr>"
        for d in weekly.days
    )
    fuel_items = "".join(
        f"<li>{k.replace('_', ' ')}: <b>{v:,.0f}</b></li>"
        for k, v in fuel.estimated_fuel_avoided.items()
    )
    li = lambda items: "".join(f"<li>{i}</li>" for i in items)  # noqa: E731

    body = f"""
<header class="rpt"><h1>🔥 SCORCH Heat Risk Report</h1>
<div class="sub">{asset['name']} — generated from free public data (SCORCH Level 0)</div></header>
<div class="disclaimer"><b>{PUBLIC_DATA_DISCLAIMER}</b> Confidence:
{risk_model.confidence_level(r['weather'])}.</div>
<div class="no-print" style="margin-bottom:10px">
  <a class="btn" href="/dashboard">← Dashboard &amp; interactive map</a>
  <a class="btn" href="/report/portfolio/kuwait">Kuwait portfolio report</a>
  <a class="btn" href="https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}">
  View location on OpenStreetMap</a>
</div>

<h2>Asset profile (public assumptions)</h2>
<div class="cards">
  <div class="card"><div class="k">Building type</div><div class="v" style="font-size:16px">{asset['building_type']}</div></div>
  <div class="card"><div class="k">Area</div><div class="v" style="font-size:16px">{asset['area_m2']:,.0f} m²</div></div>
  <div class="card"><div class="k">Operating hours</div><div class="v" style="font-size:16px">{oh['start_hour']:02d}:00–{oh['end_hour']:02d}:00</div></div>
  <div class="card"><div class="k">Location</div><div class="v" style="font-size:16px">{lat:.4f}, {lon:.4f}</div><div class="s">Kuwait</div></div>
</div>

<h2>Today / tomorrow heat risk (48h)</h2>
<div class="cards">
  <div class="card"><div class="k">Heat risk score</div><div class="v">{risk['score']:.0f}/100</div><div class="s">{_chip(risk['category'])}</div></div>
  <div class="card"><div class="k">Max temperature</div><div class="v">{risk['max_temp_c']:.1f} °C</div><div class="s">{risk['hours_above_45c']} h ≥ 45 °C</div></div>
  <div class="card"><div class="k">Peak cooling window</div><div class="v">{window.start_hour:02d}–{window.end_hour:02d}h</div><div class="s">protect this window</div></div>
  <div class="card"><div class="k">Est. peak demand</div><div class="v">{demand['peak_demand_mw']:.1f} MW</div><div class="s">around {demand['peak_hour'][11:16]}</div></div>
</div>

<h2>Baseline vs SCORCH-recommended operation (estimates)</h2>
<div class="cards">
  <div class="card"><div class="k">Baseline peak</div><div class="v">{max(scenario.baseline_mw):.1f} MW</div></div>
  <div class="card"><div class="k">SCORCH peak</div><div class="v">{max(scenario.scorch_mw):.1f} MW</div></div>
  <div class="card"><div class="k">Peak reduction</div><div class="v">−{scenario.peak_reduction_mw:.1f} MW</div><div class="s">{scenario.peak_reduction_pct}% (estimate)</div></div>
  <div class="card"><div class="k">Daily energy change</div><div class="v">{scenario.daily_energy_change_pct:+.1f}%</div><div class="s">shifted, not deleted</div></div>
</div>
<p class="muted">{scenario.note}</p>

<h2>Estimated grid / fuel impact of the peak reduction</h2>
<div class="cards">
  <div class="card"><div class="k">Avoided energy</div><div class="v">{fuel.avoided_mwh:.1f} MWh</div><div class="s">over the {duration}h window</div></div>
  <div class="card"><div class="k">Avoided CO₂</div><div class="v">{fuel.estimated_emissions_avoided['co2_tonnes']:.1f} t</div><div class="s">{fuel.generator_label}</div></div>
</div>
<ul>{fuel_items}</ul>
<p class="muted">Order-of-magnitude only; does not model actual Kuwait dispatch.</p>

<h2>7-day outlook ({weekly.weather_source}{'' if weekly.is_live else ' — offline fallback'})</h2>
<table><tr><th>Date</th><th>Max °C</th><th>Feels-like °C</th><th>CDH</th>
<th>Risk</th><th>Peak window</th><th>Daily action</th></tr>{weekly_rows}</table>

<h2>Recommendations</h2>
<p><b>Pre-cooling:</b> {plan.pre_cooling_window}<br>
<b>Peak protection:</b> {plan.peak_protection_window}</p>
<p><b>Non-critical zone reductions</b></p><ul>{li(plan.noncritical_zone_reductions)}</ul>
<p><b>Readiness checks</b></p><ul>{li(plan.readiness_checks)}</ul>
<p><b>What NOT to do</b></p><ul>{li(plan.what_not_to_do)}</ul>

<h2>Assumptions</h2><ul>{li(risk_model.model_assumptions(r['req'], r['weather']))}</ul>
<h2>Data sources used</h2>
<ul><li>Open-Meteo hourly forecast (free, no API key) — or the synthetic Kuwait
hot-day fallback when offline (this run: <b>{r['weather'].source}</b>).</li>
<li>OpenStreetMap for the map layer and location links (© OSM contributors, ODbL).</li>
<li>Public building archetype intensities and public asset assumptions
(approximate GLA, coordinates, operating hours).</li></ul>
<h2>What private data would improve accuracy</h2><ul>{li(DATA_UPGRADES)}</ul>
"""
    return _page(f"SCORCH report — {asset['name']}", body)


def portfolio_report_html() -> str:
    """Rank all built-in Kuwait example assets by heat/cooling risk."""
    rows = []
    total_reduction = 0.0
    for slug in EXAMPLE_ASSETS:
        r = _run_asset_pipeline(slug)
        total_reduction += max(r["scenario"].peak_reduction_mw, 0.0)
        rows.append((slug, r))
    rows.sort(key=lambda x: x[1]["risk"]["score"], reverse=True)

    fuel = compute_fuel_impact(FuelImpactRequest(
        peak_reduction_mw=total_reduction, duration_hours=5, generator_type="generic_grid"
    ))

    table_rows = "".join(
        f"<tr><td>{i+1}</td><td><a href='/report/{slug}'>{r['asset']['name']}</a></td>"
        f"<td>{r['asset']['building_type']}</td>"
        f"<td>{r['asset']['area_m2']:,.0f}</td>"
        f"<td>{r['risk']['score']:.0f} {_chip(r['risk']['category'])}</td>"
        f"<td>{r['risk']['max_temp_c']:.1f}</td>"
        f"<td>{r['window'].start_hour:02d}:00–{r['window'].end_hour:02d}:00</td>"
        f"<td>{r['demand']['peak_demand_mw']:.1f}</td>"
        f"<td>−{r['scenario'].peak_reduction_mw:.1f}</td></tr>"
        for i, (slug, r) in enumerate(rows)
    )

    body = f"""
<header class="rpt"><h1>🔥 SCORCH Kuwait Portfolio Report</h1>
<div class="sub">{len(rows)} example assets ranked by 48h heat/cooling risk — public data only</div></header>
<div class="disclaimer"><b>{PUBLIC_DATA_DISCLAIMER}</b> All assets use public
assumptions (approximate coordinates, areas, archetype intensities).</div>
<div class="no-print" style="margin-bottom:10px">
  <a class="btn" href="/dashboard">← Dashboard &amp; interactive map</a></div>

<h2>Portfolio risk ranking</h2>
<table><tr><th>#</th><th>Asset</th><th>Type</th><th>Area m²</th><th>Risk</th>
<th>Max °C</th><th>Peak window</th><th>Est. peak MW</th><th>SCORCH cut MW</th></tr>
{table_rows}</table>

<h2>If every asset follows its SCORCH plan (estimates)</h2>
<div class="cards">
  <div class="card"><div class="k">Combined peak reduction</div><div class="v">−{total_reduction:.1f} MW</div></div>
  <div class="card"><div class="k">Avoided energy (5h window)</div><div class="v">{fuel.avoided_mwh:.0f} MWh</div></div>
  <div class="card"><div class="k">Avoided CO₂</div><div class="v">{fuel.estimated_emissions_avoided['co2_tonnes']:.0f} t</div><div class="s">{fuel.generator_label}</div></div>
</div>
<p class="muted">Order-of-magnitude screening estimates; not verified against meters
or actual grid dispatch. Click an asset name for its full report.</p>
"""
    return _page("SCORCH Kuwait portfolio report", body)


def grid_report_html() -> str:
    """Printable Grid-Aware Kuwait public-data summary report."""
    overview = grid_model.climate_grid_overview(0)
    peak = grid_model.climate_grid_overview("peak7d")
    layer = grid_model.demand_layer(0)
    dispatch = grid_model.dispatch_simulate(DispatchRequest(
        total_estimated_load_mw=overview["estimated_total_demand_mw"],
        temperature_c=overview["temperature_c"],
    ))
    stress = overview["grid_stress"]
    ci = overview["climate_impact"]
    pci = peak["climate_impact"]  # cooling pressure is most meaningful at the peak

    def _cap(st: dict) -> str:
        cap = st["capacity_mw"]
        return "n/a (not confidently public)" if cap is None else f"{cap:,.0f}"

    station_rows = "".join(
        f"<tr><td>{st['name']}</td><td>{st['fuel_type']}</td>"
        f"<td>{st['generation_type']}</td>"
        f"<td>{_cap(st)}</td>"
        f"<td>{st['confidence']}</td></tr>"
        for st in POWER_STATIONS
    )
    district_rows = "".join(
        f"<tr><td>{p['name']}</td><td>{p['estimated_demand_mw']:,.0f}</td>"
        f"<td>{p['estimated_cooling_mw']:,.0f}</td>"
        f"<td>{p['cooling_share']:.0%}</td>"
        f"<td>{p['peak_risk']}</td>"
        f"<td>{', '.join(p['dominant_types'])}</td></tr>"
        for p in (f["properties"] for f in sorted(
            layer["features"],
            key=lambda f: f["properties"]["estimated_demand_mw"], reverse=True))
    )
    fuel_rows = "".join(
        f"<tr><td>{fuel.replace('_', ' ')}</td><td>{e['mwh']:,.0f}</td>"
        f"<td>{e['energy_gj']:,.0f}</td>"
        f"<td>{e.get('volume_m3', e.get('volume_litres', 0)):,.0f} "
        f"{'m³' if 'volume_m3' in e else 'L'}</td></tr>"
        for fuel, e in dispatch.estimated_fuel_burn_per_hour.items()
    )
    li = lambda items: "".join(f"<li>{i}</li>" for i in items)  # noqa: E731

    body = f"""
<header class="rpt"><h1>⚡ SCORCH Grid-Aware Kuwait Report</h1>
<div class="sub">Public-data grid digital shadow — Level 0 screening</div></header>
<div class="disclaimer"><b>{GRID_DISCLAIMER}</b> SCORCH estimates climate-driven
grid stress from public data. Verified deployment requires MEWRE/utility meter,
SCADA, dispatch, and fuel telemetry access.</div>
<div class="no-print" style="margin-bottom:10px">
  <a class="btn" href="/grid">← Grid dashboard</a>
  <a class="btn" href="/dashboard">Asset dashboard</a></div>

<h2>Current estimated situation ({overview['when']}, {overview['timestamp']})</h2>
<div class="cards">
  <div class="card"><div class="k">Temperature</div><div class="v">{overview['temperature_c']:.1f} °C</div>
    <div class="s">feels like {overview['apparent_temperature_c'] or '–'} °C · {overview['weather_source']}</div></div>
  <div class="card"><div class="k">Est. metro demand</div><div class="v">{overview['estimated_total_demand_mw']:,.0f} MW</div>
    <div class="s">≈ {overview['estimated_national_demand_mw']:,.0f} MW national est. (assumed 70% coverage)</div></div>
  <div class="card"><div class="k">Est. cooling demand</div><div class="v">{overview['estimated_cooling_demand_mw']:,.0f} MW</div>
    <div class="s">{overview['estimated_cooling_demand_mw']/max(overview['estimated_total_demand_mw'],1)*100:.0f}% of estimated load</div></div>
  <div class="card"><div class="k">Grid stress (est.)</div>
    <div class="v"><span class="chip" style="background:{stress['color']}">{stress['level']}</span></div>
    <div class="s">demand/capacity ≈ {stress['demand_to_capacity_ratio']}</div></div>
</div>
<p class="muted">7-day peak scenario: {peak['estimated_total_demand_mw']:,.0f} MW estimated at
{peak['temperature_c']:.1f} °C ({peak['timestamp']}), stress level {peak['grid_stress']['level']}.</p>

<h2>Power station layer (public-data profiles)</h2>
<table><tr><th>Station</th><th>Fuel</th><th>Technology</th><th>≈ MW</th><th>Confidence</th></tr>
{station_rows}</table>
<p class="muted">Coordinates approximate; capacities are approximate public figures;
'mixed'/'unknown' used where not confidently public. Transmission corridors shown on the
map are illustrative fallbacks unless OSM power=line data is loaded.</p>

<h2>District demand layer (estimated, aggregated)</h2>
<table><tr><th>District cell</th><th>Est. MW</th><th>Est. cooling MW</th>
<th>Cooling share</th><th>Peak risk</th><th>Dominant building types</th></tr>
{district_rows}</table>
<p class="muted">Homes are aggregated to district cells by design — no household
identity or per-meter consumption is shown or known.</p>

<h2>Climate-driven cooling pressure (at the 7-day peak, {peak['temperature_c']:.1f} °C)</h2>
<div class="cards">
  <div class="card"><div class="k">Added cooling vs 35 °C day</div><div class="v">+{pci['added_cooling_mw_vs_35c']:,.0f} MW</div></div>
  <div class="card"><div class="k">Added gas burn (est.)</div><div class="v">{pci['added_gas_burn_gj_per_hour']:,.0f} GJ/h</div></div>
  <div class="card"><div class="k">Added CO₂ (est.)</div><div class="v">{pci['added_co2_tonnes_per_hour']:,.0f} t/h</div></div>
  <div class="card"><div class="k">Most stressed cell</div><div class="v" style="font-size:15px">{pci['most_stressed_district']}</div>
    <div class="s">{', '.join(pci['most_stressed_building_types'])}</div></div>
</div>
<p class="muted">Right now ({overview['temperature_c']:.1f} °C): +{ci['added_cooling_mw_vs_35c']:,.0f} MW added cooling vs a 35 °C reference day.</p>

<h2>Simulated dispatch / fuel burn (scenario: {dispatch.scenario})</h2>
<div class="cards">
  <div class="card"><div class="k">Generation needed</div><div class="v">{dispatch.estimated_generation_needed_mw:,.0f} MW</div><div class="s">incl. assumed losses</div></div>
  <div class="card"><div class="k">Est. reserve</div><div class="v">{dispatch.estimated_reserve_mw:,.0f} MW</div><div class="s">{dispatch.reserve_status}</div></div>
  <div class="card"><div class="k">Est. CO₂</div><div class="v">{dispatch.estimated_emissions_per_hour['co2_tonnes']:,.0f} t/h</div></div>
  <div class="card"><div class="k">Marginal plant (assumed)</div><div class="v" style="font-size:14px">{dispatch.estimated_marginal_plant}</div></div>
</div>
<table><tr><th>Fuel</th><th>MWh/h</th><th>Energy GJ/h</th><th>Volume/h</th></tr>{fuel_rows}</table>

<h2>Limitations</h2>
<ul>
<li>This is a public-data digital shadow: district demand, dispatch shares, fuel burn,
and stress are all screening estimates from assumptions listed above.</li>
<li>No MEWRE meter, SCADA, dispatch, or fuel telemetry is used — and none is claimed.</li>
<li>OSM power/building coverage in Kuwait is incomplete; fallback layers are labelled.</li>
<li>Weather is a point forecast at the metro centre; microclimates are not modelled.</li>
</ul>

<h2>Public data sources used</h2>
<ul>
<li>Open-Meteo hourly forecast (free, no key) — this run: {overview['weather_source']}.</li>
<li>OpenStreetMap / Overpass for power infrastructure and building footprints (ODbL).</li>
<li>Public reports for approximate power-station names/locations/capacities.</li>
<li>Built-in labelled fallbacks when live sources are unavailable.</li>
</ul>

<h2>Next data needed from MEWRE/utility for verified deployment</h2>
<ul>{li([
    "Hourly national and per-substation load (SCADA/EMS extracts).",
    "Actual dispatch schedules and unit commitments per station.",
    "Fuel consumption telemetry per station (gas/HFO/gasoil).",
    "Feeder-level topology and ratings for real congestion analysis.",
    "Smart-meter aggregates per district (privacy-preserving).",
])}</ul>
"""
    return _page("SCORCH Grid-Aware Kuwait report", body)
