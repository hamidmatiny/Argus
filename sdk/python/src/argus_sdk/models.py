"""Typed models — TelemetryEvent mirrors shared/contracts/v1; gateway DTOs for REST."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Keep in lockstep with shared/contracts/v1/models.py (Phase 1).
VEHICLE_ID_PATTERN = r"^VH-[0-9]{4,8}$"


class DeviceType(str, Enum):
    UNSPECIFIED = "DEVICE_TYPE_UNSPECIFIED"
    VEHICLE = "DEVICE_TYPE_VEHICLE"
    EDGE_GATEWAY = "DEVICE_TYPE_EDGE_GATEWAY"
    SIMULATOR = "DEVICE_TYPE_SIMULATOR"


class SensorStatus(str, Enum):
    UNSPECIFIED = "SENSOR_STATUS_UNSPECIFIED"
    OK = "SENSOR_STATUS_OK"
    DEGRADED = "SENSOR_STATUS_DEGRADED"
    FAULT = "SENSOR_STATUS_FAULT"


class TelemetryEvent(BaseModel):
    """In-process validation mirror of argus.v1.TelemetryEvent (Phase 1 contract)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    vehicle_id: str = Field(..., pattern=VEHICLE_ID_PATTERN)
    trip_id: str = Field(..., min_length=1)
    timestamp: datetime
    gps_lat: float = Field(..., ge=-90.0, le=90.0)
    gps_lon: float = Field(..., ge=-180.0, le=180.0)
    speed_mph: float = Field(..., ge=0.0, le=120.0)
    brake_pressure: float = Field(..., ge=0.0)
    lidar_temp_c: float
    compute_load_pct: float = Field(..., ge=0.0, le=100.0)
    sensor_status: SensorStatus
    hardware_version: str = Field(..., min_length=1)
    device_type: DeviceType

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> object:
        if value is None or value == "":
            raise ValueError("timestamp is required")
        return value

    @model_validator(mode="after")
    def _reject_unspecified_enums(self) -> Self:
        if self.sensor_status == SensorStatus.UNSPECIFIED:
            raise ValueError("sensor_status must not be UNSPECIFIED")
        if self.device_type == DeviceType.UNSPECIFIED:
            raise ValueError("device_type must not be UNSPECIFIED")
        return self

    def to_avro_record(self) -> dict[str, Any]:
        """Serialize for Confluent Avro wire format (ISO timestamp + enum strings)."""
        data = self.model_dump(mode="json")
        return data


class IncidentSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    incident_id: str
    vehicle_id: str | None = None
    severity: str | None = None
    status: str | None = None
    source_service: str | None = None
    timestamp: str | None = None
    reason: str | None = None
    summary: str | None = None
    open: bool | None = None


class TelemetryQueryResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0


class RetrainResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str | None = None
    status: str | None = None
    message: str | None = None
