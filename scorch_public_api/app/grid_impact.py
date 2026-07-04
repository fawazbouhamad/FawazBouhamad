"""Grid/fuel impact of a SCORCH peak reduction — transparent approximations.

All factors are round, public-domain engineering numbers (typical heat
rates and standard fuel emission factors). They deliberately do NOT model
actual Kuwait dispatch, plant mix, or marginal pricing — outputs are
order-of-magnitude screening estimates.
"""

from __future__ import annotations

from .models import FuelImpactRequest, FuelImpactResponse

# Per-MWh(electric) assumptions by generator type.
#   fuel: unit-keyed quantities avoided per avoided MWh
#   co2_t_per_mwh: standard fuel emission factors at the assumed heat rate
GENERATORS: dict[str, dict] = {
    "combined_cycle_gas": {
        "label": "Combined-cycle gas turbine (~50% efficient)",
        "fuel": {"natural_gas_gj": 7.2, "natural_gas_m3": 190.0},
        "co2_t_per_mwh": 0.40,
    },
    "simple_cycle_gas": {
        "label": "Simple-cycle gas turbine (~33% efficient, peaker)",
        "fuel": {"natural_gas_gj": 10.9, "natural_gas_m3": 287.0},
        "co2_t_per_mwh": 0.61,
    },
    "diesel_backup": {
        "label": "Diesel backup generator (~0.27 L/kWh)",
        "fuel": {"diesel_litres": 270.0},
        "co2_t_per_mwh": 0.72,
    },
    "fuel_oil_steam": {
        "label": "Heavy fuel oil steam plant (~33% efficient)",
        "fuel": {"heavy_fuel_oil_litres": 270.0, "heavy_fuel_oil_gj": 10.9},
        "co2_t_per_mwh": 0.84,
    },
    "generic_grid": {
        "label": "Generic GCC grid mix (gas/oil thermal, approximate)",
        "fuel": {"mixed_thermal_fuel_gj": 9.5},
        "co2_t_per_mwh": 0.60,
    },
}


def compute_fuel_impact(req: FuelImpactRequest) -> FuelImpactResponse:
    gen = GENERATORS[req.generator_type]
    avoided_mwh = round(req.peak_reduction_mw * req.duration_hours, 3)

    fuel = {unit: round(avoided_mwh * qty, 1) for unit, qty in gen["fuel"].items()}
    emissions = {"co2_tonnes": round(avoided_mwh * gen["co2_t_per_mwh"], 2)}

    return FuelImpactResponse(
        generator_type=req.generator_type,
        generator_label=gen["label"],
        avoided_mwh=avoided_mwh,
        estimated_fuel_avoided=fuel,
        estimated_emissions_avoided=emissions,
        confidence="low-medium (typical heat rates + standard emission factors)",
        assumptions=[
            f"avoided_mwh = peak_reduction_mw ({req.peak_reduction_mw}) x "
            f"duration_hours ({req.duration_hours}).",
            f"Generator assumption: {gen['label']}.",
            f"Emission factor {gen['co2_t_per_mwh']} tCO2/MWh at the assumed heat rate.",
            "This does NOT model actual Kuwait dispatch, plant mix, transmission "
            "losses, or marginal pricing — order-of-magnitude screening only.",
        ],
    )
