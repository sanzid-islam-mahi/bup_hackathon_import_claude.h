"""
Pydantic schemas for the GridWise /optimize-energy contract.

These mirror the canonical Problem Statement. Field names must match exactly.
Validation enforces: 24 unique hours 0-23 ascending, hours arrays 0-23,
factors in [0,1], non-negative numerics.
"""
from __future__ import annotations

from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


# ============ Request ============

class HourEntry(BaseModel):
    hour: int = Field(ge=0, le=23)
    demand_kwh: float = Field(ge=0)
    solar_kwh: float = Field(ge=0)
    tariff_bdt_per_kwh: float = Field(ge=0)


class BatterySpec(BaseModel):
    capacity_kwh: float = Field(gt=0)
    initial_energy_kwh: float = Field(ge=0)
    minimum_energy_kwh: float = Field(ge=0)
    max_charge_kwh_per_hour: float = Field(ge=0)
    max_discharge_kwh_per_hour: float = Field(ge=0)


class OptimizeRequest(BaseModel):
    scenario_id: str
    operator_notes: List[str] = Field(min_length=1, max_length=3)
    hours: List[HourEntry] = Field(min_length=24, max_length=24)
    battery: BatterySpec

    @field_validator("operator_notes")
    @classmethod
    def notes_non_empty(cls, v: List[str]) -> List[str]:
        if any(not n or not n.strip() for n in v):
            raise ValueError("operator_notes must be non-empty strings")
        return [n.strip() for n in v]

    @field_validator("hours")
    @classmethod
    def hours_valid(cls, v: List[HourEntry]) -> List[HourEntry]:
        hs = [h.hour for h in v]
        if sorted(hs) != list(range(24)):
            raise ValueError("hours must contain exactly one of each 0-23")
        return v

    @model_validator(mode="after")
    def check_battery(self):
        b = self.battery
        if b.minimum_energy_kwh > b.capacity_kwh:
            raise ValueError("battery minimum_energy_kwh > capacity_kwh")
        if b.initial_energy_kwh > b.capacity_kwh:
            raise ValueError("battery initial_energy_kwh > capacity_kwh")
        if b.initial_energy_kwh < b.minimum_energy_kwh:
            raise ValueError("battery initial_energy_kwh < minimum_energy_kwh")
        return self


# ============ Directive interpretation ============

DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]


class SolarReduction(BaseModel):
    hours: List[int] = Field(min_length=1)
    factor: float = Field(ge=0.0, le=1.0)

    @field_validator("hours")
    @classmethod
    def hours_asc(cls, v: List[int]) -> List[int]:
        if sorted(set(v)) != v:
            raise ValueError("hours must be unique ascending 0-23")
        if any(h < 0 or h > 23 for h in v):
            raise ValueError("hours must be 0-23")
        return v


class MinimumBatteryReserve(BaseModel):
    hours: List[int] = Field(min_length=1)
    minimum_energy_kwh: float = Field(ge=0)

    @field_validator("hours")
    @classmethod
    def hours_asc(cls, v: List[int]) -> List[int]:
        if sorted(set(v)) != v:
            raise ValueError("hours must be unique ascending 0-23")
        if any(h < 0 or h > 23 for h in v):
            raise ValueError("hours must be 0-23")
        return v


class NoChargeWindow(BaseModel):
    hours: List[int] = Field(min_length=1)

    @field_validator("hours")
    @classmethod
    def hours_asc(cls, v: List[int]) -> List[int]:
        if sorted(set(v)) != v:
            raise ValueError("hours must be unique ascending 0-23")
        if any(h < 0 or h > 23 for h in v):
            raise ValueError("hours must be 0-23")
        return v


class NoDischargeWindow(BaseModel):
    hours: List[int] = Field(min_length=1)

    @field_validator("hours")
    @classmethod
    def hours_asc(cls, v: List[int]) -> List[int]:
        if sorted(set(v)) != v:
            raise ValueError("hours must be unique ascending 0-23")
        if any(h < 0 or h > 23 for h in v):
            raise ValueError("hours must be 0-23")
        return v


class MaxGridWindow(BaseModel):
    hours: List[int] = Field(min_length=1)
    max_grid_kwh: float = Field(ge=0)

    @field_validator("hours")
    @classmethod
    def hours_asc(cls, v: List[int]) -> List[int]:
        if sorted(set(v)) != v:
            raise ValueError("hours must be unique ascending 0-23")
        if any(h < 0 or h > 23 for h in v):
            raise ValueError("hours must be 0-23")
        return v


StructuredAdjustment = Union[
    SolarReduction,
    MinimumBatteryReserve,
    NoChargeWindow,
    NoDischargeWindow,
    MaxGridWindow,
    None,
]


class DirectiveInterpretation(BaseModel):
    note_index: int = Field(ge=0)
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: Optional[dict] = None
    explanation: str

    @model_validator(mode="after")
    def check_structured_adjustment(self):
        """Re-validate structured_adjustment against the matching specialized model.

        This is the second layer of defense: the interpreter's _shape_adjustment
        already returns shapes that match the models below, but if any caller
        constructs DirectiveInterpretation directly, this enforces that the shape
        is correct for the declared directive_type.
        """
        dt = self.directive_type
        adj = self.structured_adjustment
        if dt == "no_op":
            if self.applies is not False:
                raise ValueError("no_op requires applies=false")
            if adj is not None:
                raise ValueError("no_op requires structured_adjustment=null")
            return self
        if self.applies is not True:
            raise ValueError(f"{dt} requires applies=true")
        if adj is None:
            raise ValueError(f"{dt} requires structured_adjustment")
        # Validate against the matching specialized model
        model_map = {
            "solar_reduction": SolarReduction,
            "minimum_battery_reserve": MinimumBatteryReserve,
            "no_charge_window": NoChargeWindow,
            "no_discharge_window": NoDischargeWindow,
            "max_grid_window": MaxGridWindow,
        }
        model_cls = model_map.get(dt)
        if model_cls is not None:
            try:
                model_cls.model_validate(adj)
            except ValidationError as e:
                raise ValueError(
                    f"structured_adjustment does not match {dt}: {e}"
                ) from e
        return self


# ============ Hourly plan ============

BatteryAction = Literal["charge", "discharge", "idle"]


class HourlyPlanEntry(BaseModel):
    hour: int = Field(ge=0, le=23)
    grid_kwh: float = Field(ge=0)
    solar_used_kwh: float = Field(ge=0)
    battery_action: BatteryAction
    battery_kwh: float = Field(ge=0)
    battery_energy_after_kwh: float = Field(ge=0)

    @model_validator(mode="after")
    def check_idle_zero(self):
        if self.battery_action == "idle" and self.battery_kwh != 0:
            raise ValueError("idle requires battery_kwh=0")
        return self


# ============ Response ============

class OptimizeResponse(BaseModel):
    scenario_id: str
    directive_interpretation: List[DirectiveInterpretation]
    hourly_plan: List[HourlyPlanEntry] = Field(min_length=24, max_length=24)
    total_grid_kwh: float = Field(ge=0)
    total_cost_bdt: float = Field(ge=0)
    peak_grid_kwh: float = Field(ge=0)
    plan_summary: str

    @field_validator("hourly_plan")
    @classmethod
    def plan_24_unique(cls, v):
        hs = [h.hour for h in v]
        if sorted(hs) != list(range(24)):
            raise ValueError("hourly_plan must have exactly hours 0-23")
        return v

    @field_validator("directive_interpretation")
    @classmethod
    def interpretations_in_order(cls, v):
        for i, d in enumerate(v):
            if d.note_index != i:
                raise ValueError(f"note_index must be {i}, got {d.note_index}")
        return v
