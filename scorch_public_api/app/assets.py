"""Public building archetypes and the 360 Mall example asset.

All numbers here are public-domain engineering assumptions for screening,
NOT measured values for any specific building. They are chosen to be
plausible for large GCC buildings and are surfaced in every API response.
"""

from __future__ import annotations

# Archetype parameters, keyed by building_type.
#   base_load_kw_m2      : always-on electrical load (lighting, plant, IT)
#   occupancy_load_kw_m2 : extra load at full occupancy (people, ventilation)
#   cooling_intensity_kw_m2 : electrical cooling intensity at reference
#                             cooling-degree conditions (see risk_model)
#   heat_sensitivity     : multiplier on the risk score (hospitals > mosques)
ARCHETYPES: dict[str, dict] = {
    "mall": {
        "base_load_kw_m2": 0.025,
        "occupancy_load_kw_m2": 0.020,
        "cooling_intensity_kw_m2": 0.16,
        "heat_sensitivity": 1.00,
        "label": "Mixed-use mall",
    },
    "tower": {
        "base_load_kw_m2": 0.020,
        "occupancy_load_kw_m2": 0.015,
        "cooling_intensity_kw_m2": 0.12,
        "heat_sensitivity": 0.95,
        "label": "Commercial/residential tower",
    },
    "school": {
        "base_load_kw_m2": 0.012,
        "occupancy_load_kw_m2": 0.018,
        "cooling_intensity_kw_m2": 0.10,
        "heat_sensitivity": 0.90,
        "label": "School",
    },
    "hospital": {
        "base_load_kw_m2": 0.040,
        "occupancy_load_kw_m2": 0.015,
        "cooling_intensity_kw_m2": 0.18,
        "heat_sensitivity": 1.15,
        "label": "Hospital (critical comfort)",
    },
    "mosque": {
        "base_load_kw_m2": 0.008,
        "occupancy_load_kw_m2": 0.025,
        "cooling_intensity_kw_m2": 0.11,
        "heat_sensitivity": 0.85,
        "label": "Mosque (intermittent occupancy)",
    },
    "factory": {
        "base_load_kw_m2": 0.050,
        "occupancy_load_kw_m2": 0.008,
        "cooling_intensity_kw_m2": 0.10,
        "heat_sensitivity": 1.05,
        "label": "Factory/industrial",
    },
    "generic": {
        "base_load_kw_m2": 0.020,
        "occupancy_load_kw_m2": 0.015,
        "cooling_intensity_kw_m2": 0.13,
        "heat_sensitivity": 1.00,
        "label": "Generic large building",
    },
}

# Occupancy level -> multiplier on occupancy-driven loads and internal heat.
OCCUPANCY_FACTORS = {"low": 0.7, "medium": 1.0, "high": 1.25}

# Example asset: 360 Mall, Kuwait (public assumptions only).
MALL_360 = {
    "name": "360 Mall (example asset, public assumptions)",
    "latitude": 29.2733,  # South Surra, Kuwait — approximate public coordinates
    "longitude": 47.9770,
    "building_type": "mall",
    "area_m2": 130_000.0,  # approximate GLA from public sources
    "operating_hours": {"start_hour": 10, "end_hour": 22},
    "zones": [
        {"name": "Retail concourse", "area_share": 0.45, "internal_load_factor": 1.0, "critical_comfort": True},
        {"name": "Food court / restaurants", "area_share": 0.12, "internal_load_factor": 1.8, "critical_comfort": True},
        {"name": "Cinema", "area_share": 0.08, "internal_load_factor": 1.5, "critical_comfort": True},
        {"name": "Arena / event space", "area_share": 0.08, "internal_load_factor": 1.6, "critical_comfort": True},
        {"name": "Hotel connection", "area_share": 0.07, "internal_load_factor": 1.2, "critical_comfort": True},
        {"name": "Parking / service areas", "area_share": 0.12, "internal_load_factor": 0.4, "critical_comfort": False},
        {"name": "Back-of-house", "area_share": 0.08, "internal_load_factor": 0.6, "critical_comfort": False},
    ],
    "notes": (
        "All values are public assumptions (approximate GLA, typical zone mix). "
        "No BMS, meter, or floor-plan data was used."
    ),
}
