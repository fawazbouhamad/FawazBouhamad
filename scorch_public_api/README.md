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
| `GET /dashboard` | Interactive dashboard (vanilla HTML/JS, no CDN, works offline) |

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
│   └── assets.py           # archetypes + 360 Mall public profile
├── dashboard/
│   └── index.html          # self-contained dashboard (served at /dashboard)
├── tests/
│   └── test_risk_model.py
└── examples/
    └── sample_360_mall_request.json
```
