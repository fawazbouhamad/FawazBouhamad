# 🔥 SCORCH — Public Climate Risk API (MVP)

**Heat-driven cooling risk screening for Kuwait/GCC buildings, built entirely on free public data.**

> ⚠️ **This is a public-data estimate, not a verified meter/BMS result.** SCORCH Level 0 is a
> screening/risk/forecast tool. It does not control equipment and its numbers are
> assumption-driven estimates, returned with their assumptions and a confidence level.

## What is SCORCH?

SCORCH helps malls, towers, schools, hospitals, mosques, and factories in Kuwait and the GCC
answer three operational questions before an extreme-heat day:

1. **When will extreme heat push cooling demand up?**
2. **When is the peak cooling risk window?**
3. **What should facility managers actually do about it?**

## Why Kuwait/GCC?

- Kuwait regularly exceeds **50 °C**; air conditioning drives well over half of summer
  electricity demand.
- Cooling failures on peak days are a safety issue (malls, hospitals, schools), not just a cost issue.
- Most buildings have **no accessible BMS/meter data** for third-party tools — so SCORCH starts
  with what is public: weather forecasts, coordinates, and building archetypes.

## How the public-data MVP works

```
Open-Meteo 48h forecast (free, no API key)
        │  (falls back to a synthetic Kuwait hot-day generator if offline)
        ▼
Heat risk model ──► risk score 0–100 (max temp, cooling degree hours,
        │            hours ≥45°C, operating-hour overlap, building
        │            sensitivity, event/occupancy modifier)
        ▼
Demand model ──► total_demand_mw = base + occupancy + cooling + event
        │         cooling_load_mw = area × intensity × cooling_degree_factor
        │                            × occupancy_factor / 1000
        ▼
SCORCH scenario ──► pre-cool 08:00–12:00, trim 12:00–17:00 peak modestly
        ▼
Action plan ──► pre-cooling window, peak protection, readiness checks,
                what NOT to do
```

Risk categories: **0–30 Low · 31–55 Moderate · 56–75 High · 76–100 Very High**

The example asset is **360 Mall, Kuwait** using public assumptions only:
mixed-use mall, ~130,000 m² GLA, open 10:00–22:00, seven typical zones
(retail, food court, cinema, arena, hotel link, parking, back-of-house).

## Quick start

Requires Python 3.11+.

```bash
cd scorch_public_api
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run the API + dashboard (one process)
uvicorn app.main:app --reload
```

- **Dashboard:** http://127.0.0.1:8000/dashboard — pick 360 Mall, tweak area / type /
  hours / event day / occupancy, click **Run SCORCH simulation**.
- **API docs (Swagger):** http://127.0.0.1:8000/docs
- **Tests:** `pytest` (fully offline; weather is monkeypatched to the synthetic generator)

If Open-Meteo is unreachable, the app automatically uses the built-in synthetic Kuwait
hot-day generator and marks confidence as `low`.

## Example curl commands

```bash
# API index
curl http://127.0.0.1:8000/

# Example asset profile (360 Mall, public assumptions)
curl http://127.0.0.1:8000/assets/example/360-mall

# Heat risk for the 360 Mall (uses examples/sample_360_mall_request.json)
curl -X POST http://127.0.0.1:8000/risk/heat \
  -H "Content-Type: application/json" \
  -d @examples/sample_360_mall_request.json

# Hourly demand estimate + SCORCH baseline-vs-recommended scenario
curl -X POST http://127.0.0.1:8000/cooling/estimate \
  -H "Content-Type: application/json" \
  -d @examples/sample_360_mall_request.json

# Action plan for a Very High risk day
curl -X POST http://127.0.0.1:8000/actions/recommend \
  -H "Content-Type: application/json" \
  -d '{"risk_score": 85, "building_type": "mall", "peak_window_start_hour": 12, "peak_window_end_hour": 17, "event_day": true}'

# Full 360 Mall demo (weather → risk → demand → scenario → actions → summary)
curl "http://127.0.0.1:8000/demo/360-mall?event_day=true&occupancy_level=high"
```

## API endpoints

| Endpoint | What it does |
|---|---|
| `GET /` | API name, version, endpoint index |
| `GET /assets/example/360-mall` | 360 Mall public asset profile |
| `POST /risk/heat` | Hourly temps, cooling degree hours, risk score 0–100, peak window, confidence, assumptions |
| `POST /cooling/estimate` | Hourly total/baseline/cooling MW, peak MW & hour, risk category, SCORCH scenario |
| `POST /actions/recommend` | Pre-cooling window, peak protection, reductions, readiness checks, what NOT to do |
| `GET /demo/360-mall` | Full pipeline for 360 Mall + plain-English executive summary |
| `GET /demo/{slug}/weekly` | 7-day daily outlook: max/feels-like temp, CDH, risk, window, action |
| `POST /grid/fuel-impact` | Avoided MWh, fuel, CO₂ for a peak reduction (5 generator archetypes) |
| `GET /report/{slug}` | Printable HTML heat-risk report for one asset |
| `GET /report/portfolio/kuwait` | Printable portfolio report ranking all example assets |
| `GET /map/assets` | Built-in example assets as a GeoJSON FeatureCollection |
| `GET /map/assets/{slug}` | One example asset as GeoJSON (404 if unknown) |
| `GET /map/risk-layer` | Risk-scored GeoJSON layer (marker colors, peak windows, summaries) |
| `GET /map/buildings/nearby?lat=&lon=&radius_m=` | OSM footprints via Overpass, with offline fallback geometry |
| `GET /dashboard` | Interactive dashboard with Kuwait asset map (simulator works offline) |

## Demo Pack v1

Everything needed to demo SCORCH to a professor, investor, incubator, or facility manager —
still 100% free public data, no keys, runs locally.

**How to run:** same as Quick start (`uvicorn app.main:app --reload`), then open:

| URL | What you'll see |
|---|---|
| `http://127.0.0.1:8000/dashboard` | Interactive dashboard: asset selector, map, simulation, 7-day outlook, grid impact |
| `http://127.0.0.1:8000/report/360-mall` | Printable heat-risk report for 360 Mall (Ctrl/Cmd+P → PDF) |
| `http://127.0.0.1:8000/report/portfolio/kuwait` | Kuwait portfolio report — all example assets ranked by risk |
| `http://127.0.0.1:8000/demo/360-mall/weekly` | 7-day outlook JSON |
| `http://127.0.0.1:8000/docs` | OpenAPI docs for the whole API |

**Suggested screenshots for a pitch deck:**
1. Dashboard with the risk layer enabled on the map (colored Kuwait asset markers).
2. Dashboard after "Run SCORCH simulation" — risk tiles + baseline-vs-SCORCH chart.
3. The 7-day outlook table (dashboard or asset report).
4. The asset report header + risk cards (print preview looks clean).
5. The portfolio report ranking table.

**Grid/fuel impact** (`POST /grid/fuel-impact`): converts a peak reduction into avoided
MWh, fuel, and CO₂ using typical heat rates and standard emission factors for five
generator archetypes (combined-cycle gas, simple-cycle gas, diesel backup, fuel-oil
steam, generic GCC grid mix). Order-of-magnitude only — it does **not** model actual
Kuwait dispatch.

**What the model CAN claim:** screening-grade heat-risk ranking, timing of the peak
cooling window from a real public forecast, direction and rough size of pre-cooling
benefits, order-of-magnitude fuel/CO₂ impact.
**What it CANNOT claim:** verified kW/kWh savings, actual building loads, actual grid
dispatch or prices, comfort outcomes in specific zones. Every response says so.

**Why this matters for Kuwait/GCC:** cooling is most of summer peak demand; a screening
tool that needs zero private data means a facility manager can see their risk profile
*before* any integration work, and the upgrade path (bills → meters → BMS) is where the
accuracy — and the business — grows.

## Map Layer Strategy

The dashboard includes a Kuwait asset map built strictly on free/open geodata:

- **Prototype: Leaflet + OpenStreetMap raster tiles.** Leaflet (BSD-2) is loaded from a
  public CDN; `tile.openstreetmap.org` is used for the basemap with proper attribution.
  **Public OSM tiles are for prototype/light usage only** — the OSMF tile usage policy does
  not allow heavy production traffic.
- **Building footprints: OSM Overpass API, optional.** `/map/buildings/nearby` queries
  Overpass for real footprints; if Overpass is slow, down, or empty, the endpoint returns
  fallback geometry (asset point + approximate square buffer sized from the public area
  assumption) tagged `source: fallback_public_assumption` — the map never breaks offline.
- **Open-data direction:** OSM, [Overture Maps](https://overturemaps.org/), and Microsoft's
  open Building Footprints datasets are the correct long-term sources for building geometry.
- **Google Maps/Google Earth are NOT SCORCH data sources.** They are not free/open
  extraction sources (licensing prohibits it). Google may only be used as a manual visual
  reference by a human, never as an API or scraped data source.
- **Production path:** self-host raster/vector tiles (e.g. OpenMapTiles/Protomaps
  **PMTiles**) or use a usage-compliant tile provider, and pre-bake footprint extracts
  from OSM/Overture instead of live Overpass calls.

## Limitations (read this)

- **Screening-grade only.** Every load number comes from public archetype intensities
  (kW/m²), not from this building's meters. Absolute MW values can easily be ±30–50% off.
- Weather is a point forecast at the coordinates; urban heat island and microclimate
  effects are not modeled.
- Occupancy is a simple open-hours ramp; real footfall differs (Ramadan, weekends, events).
- The SCORCH scenario assumes usable thermal mass and a controllable plant; savings figures
  are **estimates of potential**, not guarantees.
- Zones affect internal-load weighting only; there is no zone-level thermal simulation.

**Private data that would improve accuracy:** hourly electricity meter data · chiller/BMS
data · indoor zone temperatures · occupancy/footfall · event calendar · floor plans/BIM.

## Upgrade path

| Level | Data | What it unlocks |
|---|---|---|
| **0 (this MVP)** | Public weather + archetypes | Risk screening, peak-window forecasting, generic action plans |
| **1** | Customer bills / hourly meters | Calibrated demand model, real baselines, measured savings |
| **2** | Floor plans / zone areas | Zone-level load split, targeted reductions |
| **3** | BMS / chiller integration | Setpoint-level recommendations, verified pre-cooling performance |
| **4** | Full digital twin | Model-predictive control, automated peak orchestration |

## Project structure

```
scorch_public_api/
├── README.md
├── requirements.txt
├── app/
│   ├── main.py             # FastAPI app + endpoints
│   ├── models.py           # Pydantic schemas (with honesty fields)
│   ├── data_sources.py     # Open-Meteo + synthetic Kuwait hot-day fallback
│   ├── risk_model.py       # risk score, demand model, SCORCH scenario
│   ├── recommendations.py  # rule-based action plans
│   ├── assets.py           # archetypes + example Kuwait assets (360 Mall etc.)
│   ├── geo_sources.py      # OSM Overpass footprints + offline fallback geometry
│   ├── map_layers.py       # GeoJSON builders + per-asset risk layer
│   ├── outlook.py          # 7-day daily heat/cooling outlook
│   ├── grid_impact.py      # avoided MWh/fuel/CO2 screening estimates
│   └── reports.py          # printable HTML asset + portfolio reports
├── dashboard/
│   └── index.html          # dashboard + Leaflet/OSM map (served at /dashboard)
├── tests/
│   ├── test_risk_model.py
│   ├── test_map_layers.py
│   └── test_demo_pack.py
└── examples/
    └── sample_360_mall_request.json
```
