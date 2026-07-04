"""Pydantic request/response models for the SCORCH Public Climate Risk API.

All models are intentionally simple. SCORCH Level 0 is a public-data
screening tool, so the schemas carry assumption/confidence fields on every
response to keep the outputs honest.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Disclaimer attached to every model output in the API.
PUBLIC_DATA_DISCLAIMER = (
    "This is a public-data estimate, not a verified meter/BMS result."
)

# Private data that would move this from a screening estimate to a
# calibrated model. Returned with every response.
DATA_UPGRADES = [
    "hourly electricity meter data",
    "chiller/BMS data",
    "indoor zone temperatures",
    "occupancy/footfall counts",
    "event calendar",
    "floor plans/BIM",
]

BuildingType = Literal[
    "mall", "tower", "school", "hospital", "mosque", "factory", "generic"
]
OccupancyLevel = Literal["low", "medium", "high"]


class OperatingHours(BaseModel):
    """Daily operating window in local hours (24h clock)."""

    start_hour: int = Field(10, ge=0, le=23)
    end_hour: int = Field(22, ge=1, le=24)

    @field_validator("end_hour")
    @classmethod
    def end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start_hour", 0)
        if v <= start:
            raise ValueError("end_hour must be after start_hour")
        return v


class Zone(BaseModel):
    """A building zone with its share of floor area.

    internal_load_factor > 1 means the zone adds more internal heat than a
    plain retail/office space (kitchens, cinema projection, event crowds).
    """

    name: str
    area_share: float = Field(..., gt=0, le=1)
    internal_load_factor: float = Field(1.0, ge=0.2, le=3.0)
    critical_comfort: bool = False


class AssetRequest(BaseModel):
    """Common input for /risk/heat and /cooling/estimate."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    building_type: BuildingType = "generic"
    area_m2: float = Field(..., gt=100, le=2_000_000)
    operating_hours: OperatingHours = OperatingHours()
    zones: Optional[list[Zone]] = None
    event_day: bool = False
    occupancy_level: OccupancyLevel = "medium"


class WeatherPoint(BaseModel):
    time: str  # ISO timestamp, local time at the site
    temp_c: float


class WeatherSeries(BaseModel):
    source: str  # "open-meteo" or "synthetic-kuwait-hot-day"
    is_live: bool
    points: list[WeatherPoint]
    note: str


class PeakWindow(BaseModel):
    start_hour: int
    end_hour: int
    description: str


class HeatRiskResponse(BaseModel):
    disclaimer: str = PUBLIC_DATA_DISCLAIMER
    weather: WeatherSeries
    hourly_temperature_c: list[float]
    cooling_degree_hours: float
    hours_above_45c: int
    max_temp_c: float
    heat_risk_score: float = Field(..., ge=0, le=100)
    risk_category: str
    peak_cooling_window: PeakWindow
    confidence: str
    assumptions: list[str]
    data_that_would_improve_accuracy: list[str] = DATA_UPGRADES


class ScenarioSeries(BaseModel):
    """Baseline vs SCORCH-recommended hourly demand, both in MW."""

    baseline_mw: list[float]
    scorch_mw: list[float]
    peak_reduction_mw: float
    peak_reduction_pct: float
    daily_energy_change_pct: float
    note: str


class CoolingEstimateResponse(BaseModel):
    disclaimer: str = PUBLIC_DATA_DISCLAIMER
    weather: WeatherSeries
    hours: list[str]
    hourly_demand_mw: list[float]
    baseline_demand_mw: list[float]  # non-cooling part (base + occupancy + event)
    cooling_demand_mw: list[float]
    peak_demand_mw: float
    peak_hour: str
    risk_category: str
    scorch_scenario: ScenarioSeries
    confidence: str
    assumptions: list[str]
    data_that_would_improve_accuracy: list[str] = DATA_UPGRADES


class ActionRequest(BaseModel):
    """Input for /actions/recommend.

    Pass the risk results you got from /risk/heat (or your own numbers).
    """

    risk_score: float = Field(..., ge=0, le=100)
    building_type: BuildingType = "generic"
    peak_window_start_hour: int = Field(12, ge=0, le=23)
    peak_window_end_hour: int = Field(17, ge=1, le=24)
    event_day: bool = False


class ActionPlan(BaseModel):
    disclaimer: str = PUBLIC_DATA_DISCLAIMER
    risk_category: str
    pre_cooling_window: str
    peak_protection_window: str
    noncritical_zone_reductions: list[str]
    readiness_checks: list[str]
    comfort_protection_notes: list[str]
    what_not_to_do: list[str]
    confidence: str
    assumptions: list[str]
    data_that_would_improve_accuracy: list[str] = DATA_UPGRADES
