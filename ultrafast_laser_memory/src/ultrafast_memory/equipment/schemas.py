from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EquipmentProfileCreate(BaseModel):
    profile_name: str
    machine_id: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    location: str | None = None
    created_by: str | None = None
    calibration_date: str | None = None
    valid_until: str | None = None
    notes: str | None = None
    laser_source: dict[str, Any] = Field(default_factory=dict)
    optical_setup: dict[str, Any] = Field(default_factory=dict)
    motion_system: dict[str, Any] = Field(default_factory=dict)
    process_capability: dict[str, Any] = Field(default_factory=dict)
    set_active: bool = False


class EquipmentProfileUpdate(BaseModel):
    profile_name: str | None = None
    machine_id: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    location: str | None = None
    status: str | None = None
    changed_by: str | None = None
    calibration_date: str | None = None
    valid_until: str | None = None
    notes: str | None = None
    laser_source: dict[str, Any] | None = None
    optical_setup: dict[str, Any] | None = None
    motion_system: dict[str, Any] | None = None
    process_capability: dict[str, Any] | None = None


class MachineBounds(BaseModel):
    equipment_profile_id: str
    revision_id: str
    machine_bounds: dict[str, list[float | int]]


class MachineBoundsOverride(BaseModel):
    machine_bounds_override: dict[str, list[float | int]] = Field(default_factory=dict)
    override_reason: str

