"""Operational recommendations by risk category.

Rule-based and deliberately conservative: SCORCH suggests load shifting and
readiness checks, never comfort sacrifice in occupied critical zones.
"""

from __future__ import annotations

from .models import ActionPlan, ActionRequest
from .risk_model import risk_category

_COMFORT_NOTES = [
    "Keep occupied comfort-critical zones (retail, food court, cinema, events, hotel) at setpoint.",
    "Pre-cooling should target 1-2 C below setpoint, not deep over-cooling.",
    "If indoor temperatures drift above comfort limits, abandon load reduction immediately.",
]

_WHAT_NOT_TO_DO = [
    "Do not switch off chillers during the peak window; cycling under extreme heat stresses compressors.",
    "Do not cut ventilation below code minimums to save energy.",
    "Do not reduce cooling in occupied food-safety areas (cold rooms, kitchens).",
    "Do not treat these public-data estimates as verified savings; validate against meter data first.",
]


def build_action_plan(req: ActionRequest) -> ActionPlan:
    category = risk_category(req.risk_score)
    peak = f"{req.peak_window_start_hour:02d}:00-{req.peak_window_end_hour:02d}:00"

    if category == "Very High":
        pre_cool = "08:00-11:30 (aggressive pre-cool, charge building thermal mass)"
        reductions = [
            "Reduce back-of-house and storage cooling setpoints by 1-2 C during the peak window.",
            "Dim/reduce parking and service-area ventilation-cooling where unoccupied.",
            "Stagger large kitchen/exhaust equipment start-ups away from the peak window.",
        ]
        checks = [
            "Test backup generators and standby chillers before noon.",
            "Verify condenser water / air-cooled condenser cleanliness before the peak.",
            "Confirm chilled-water setpoints and valve positions are per plan by 11:00.",
            "Delay noncritical maintenance, testing, and load switching until after the peak.",
            "Monitor food court, cinema, and event zones hourly during the peak window.",
        ]
    elif category == "High":
        pre_cool = "08:30-11:30 (moderate pre-cool)"
        reductions = [
            "Trim back-of-house cooling setpoints by ~1 C during the peak window.",
            "Reduce cooling to unoccupied parking/service areas.",
        ]
        checks = [
            "Confirm standby chiller availability before noon.",
            "Delay noncritical electrical testing until after the peak window.",
            "Spot-check high-internal-load zones (food court, cinema) mid-afternoon.",
        ]
    elif category == "Moderate":
        pre_cool = "09:00-11:00 (light pre-cool)"
        reductions = [
            "Optional: relax back-of-house setpoints slightly during the warmest hours.",
        ]
        checks = [
            "Routine plant walk-through; confirm no chillers are in fault.",
            "Review tomorrow's forecast for escalation.",
        ]
    else:  # Low
        pre_cool = "Not required (normal morning start-up)"
        reductions = ["None required; operate normally."]
        checks = ["Routine operation. Good day to schedule maintenance and testing."]

    return ActionPlan(
        risk_category=category,
        pre_cooling_window=pre_cool,
        peak_protection_window=(
            f"{peak}: hold pre-cooled temperatures, avoid new large loads, "
            "no chiller cycling."
        ),
        noncritical_zone_reductions=reductions,
        readiness_checks=checks,
        comfort_protection_notes=_COMFORT_NOTES,
        what_not_to_do=_WHAT_NOT_TO_DO
        + (
            ["Do not schedule additional large events during the peak window."]
            if req.event_day
            else []
        ),
        confidence="Rule-based plan driven by a public-data risk score.",
        assumptions=[
            f"Risk score {req.risk_score} -> category '{category}'.",
            f"Peak window taken as {peak} from the demand estimate.",
            "Building has some usable thermal mass for pre-cooling (typical for large GCC buildings).",
        ],
    )
