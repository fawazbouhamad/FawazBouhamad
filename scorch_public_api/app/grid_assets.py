"""Built-in Kuwait grid data: power stations, fallback transmission
corridors, and district demand cells.

HONESTY NOTES
- Power-station names/locations are public knowledge; coordinates are
  APPROXIMATE and capacities are APPROXIMATE figures from public reports.
  Where fuel/technology is not confidently public we say "mixed"/"unknown".
- Transmission corridors below are ILLUSTRATIVE fallback lines
  (source: fallback_public_assumption), not surveyed routes.
- District cells are coarse demand-aggregation rectangles with assumed
  parameters — nothing here is MEWRE meter, SCADA, or dispatch data.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Power/water stations (public-data profiles; approximate values).
# capacity_mw is an approximate public figure or None when not confident.
# ---------------------------------------------------------------------------
POWER_STATIONS: list[dict] = [
    {
        "slug": "doha-east",
        "name": "Doha East Power & Water Station",
        "latitude": 29.375, "longitude": 47.810,
        "fuel_type": "mixed",  # gas + heavy fuel oil, per public reports
        "generation_type": "steam",
        "capacity_mw": 1050.0,
        "capacity_note": "approximate public figure; older steam units",
        "confidence": "low-medium (public reports, approximate location)",
    },
    {
        "slug": "doha-west",
        "name": "Doha West Power & Water Station",
        "latitude": 29.360, "longitude": 47.785,
        "fuel_type": "mixed",
        "generation_type": "steam",
        "capacity_mw": 2400.0,
        "capacity_note": "approximate public figure (8x300 MW class)",
        "confidence": "low-medium (public reports, approximate location)",
    },
    {
        "slug": "subiya",
        "name": "Subiya (Sabiya) Power & Water Station",
        "latitude": 29.630, "longitude": 48.130,
        "fuel_type": "mixed",  # natural gas + fuel oil
        "generation_type": "combined_cycle",  # CCGT blocks + steam units on site
        "capacity_mw": 4600.0,
        "capacity_note": "approximate combined figure (steam + CCGT phases)",
        "confidence": "low-medium (public reports, approximate location)",
    },
    {
        "slug": "az-zour-south",
        "name": "Az-Zour South Power & Water Station",
        "latitude": 28.720, "longitude": 48.380,
        "fuel_type": "mixed",
        "generation_type": "unknown",  # steam + gas turbines; unit split not confident
        "capacity_mw": 5300.0,
        "capacity_note": "approximate public figure; unit breakdown uncertain",
        "confidence": "low (public reports, approximate location)",
    },
    {
        "slug": "az-zour-north",
        "name": "Az-Zour North IWPP (Phase 1)",
        "latitude": 28.735, "longitude": 48.365,
        "fuel_type": "natural_gas",
        "generation_type": "combined_cycle",
        "capacity_mw": 1540.0,
        "capacity_note": "public IWPP project figure (approximate)",
        "confidence": "medium (well-documented public IWPP project)",
    },
    {
        "slug": "shuaiba",
        "name": "Shuaiba North Power & Water Station",
        "latitude": 29.030, "longitude": 48.130,
        "fuel_type": "natural_gas",
        "generation_type": "combined_cycle",
        "capacity_mw": 875.0,
        "capacity_note": "approximate public figure for Shuaiba North CCGT",
        "confidence": "low-medium (public reports, approximate location)",
    },
    {
        "slug": "shuwaikh",
        "name": "Shuwaikh Power Station",
        "latitude": 29.355, "longitude": 47.925,
        "fuel_type": "unknown",  # peaking gas turbines historically; not confident
        "generation_type": "open_cycle_gas_turbine",
        "capacity_mw": None,
        "capacity_note": "capacity not confidently public; small peaking/desal site",
        "confidence": "low (public mentions only)",
    },
]

# Approximate public figure for national installed capacity (MW). Used only
# for the screening stress ratio; clearly an assumption.
INSTALLED_CAPACITY_MW = 19_500.0

# ---------------------------------------------------------------------------
# Fallback transmission corridors (ILLUSTRATIVE): station -> load-centre hub.
# Real routes require OSM power=line data or utility GIS.
# ---------------------------------------------------------------------------
_HUB = [47.95, 29.30]  # metro Kuwait load centre (lon, lat)

TRANSMISSION_CORRIDORS: list[dict] = [
    {"name": f"{st['name']} corridor (illustrative)",
     "coordinates": [[st["longitude"], st["latitude"]], _HUB]}
    for st in POWER_STATIONS
]

# ---------------------------------------------------------------------------
# District demand cells: coarse rectangles with assumed parameters.
#   base_mw          : non-cooling load at activity factor 1.0
#   cooling_mw_per_c : added MW per cooling-degree (above 24 C)
# Values are chosen so the metro cells sum to a plausible share of Kuwait's
# public ~17 GW summer peak. They are assumptions, not measurements.
# ---------------------------------------------------------------------------
DISTRICTS: list[dict] = [
    {"slug": "capital", "name": "Capital (Kuwait City)", "center": [29.375, 47.980],
     "half_deg": [0.035, 0.045], "base_mw": 450, "cooling_mw_per_c": 38,
     "dominant_types": ["commercial towers", "government", "residential"]},
    {"slug": "hawalli", "name": "Hawalli", "center": [29.330, 48.020],
     "half_deg": [0.025, 0.030], "base_mw": 550, "cooling_mw_per_c": 52,
     "dominant_types": ["dense residential", "retail"]},
    {"slug": "salmiya", "name": "Salmiya coastal strip", "center": [29.340, 48.075],
     "half_deg": [0.025, 0.028], "base_mw": 420, "cooling_mw_per_c": 40,
     "dominant_types": ["residential", "malls", "hospitality"]},
    {"slug": "farwaniya", "name": "Farwaniya", "center": [29.280, 47.930],
     "half_deg": [0.040, 0.045], "base_mw": 700, "cooling_mw_per_c": 62,
     "dominant_types": ["dense residential", "light industry"]},
    {"slug": "jahra", "name": "Jahra", "center": [29.340, 47.660],
     "half_deg": [0.045, 0.055], "base_mw": 380, "cooling_mw_per_c": 36,
     "dominant_types": ["residential", "agriculture/services"]},
    {"slug": "ahmadi", "name": "Ahmadi / Fahaheel", "center": [29.080, 48.080],
     "half_deg": [0.050, 0.050], "base_mw": 520, "cooling_mw_per_c": 44,
     "dominant_types": ["residential", "oil-sector industrial"]},
    {"slug": "mubarak", "name": "Mubarak Al-Kabeer / Sabah Al-Salem", "center": [29.250, 48.060],
     "half_deg": [0.030, 0.035], "base_mw": 400, "cooling_mw_per_c": 40,
     "dominant_types": ["residential", "schools"]},
    {"slug": "sulaibiya", "name": "Sulaibiya / western industrial", "center": [29.300, 47.800],
     "half_deg": [0.040, 0.050], "base_mw": 480, "cooling_mw_per_c": 30,
     "dominant_types": ["industrial", "logistics", "residential fringe"]},
]

DISTRICT_ASSUMPTIONS = [
    "District cells are coarse aggregation rectangles, not utility feeder areas.",
    "base_mw and cooling_mw_per_c are public assumptions scaled so metro cells "
    "sum to a plausible share of Kuwait's ~17 GW public summer peak.",
    "Homes are aggregated to district level by design: no household identity, "
    "ownership, or per-meter consumption is shown or known.",
    "Time-of-day activity profile is an assumption (Kuwait weekend = Fri/Sat).",
]


def district_polygon(d: dict) -> list[list[float]]:
    """Closed rectangle ring (lon, lat) for a district cell."""
    (lat, lon), (hlat, hlon) = d["center"], d["half_deg"]
    return [
        [lon - hlon, lat - hlat], [lon + hlon, lat - hlat],
        [lon + hlon, lat + hlat], [lon - hlon, lat + hlat],
        [lon - hlon, lat - hlat],
    ]
