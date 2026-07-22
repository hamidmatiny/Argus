"""Pydantic v2 models mirroring argus.v1 protobuf messages."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class IncidentSeverity(str, Enum):
    UNSPECIFIED = "INCIDENT_SEVERITY_UNSPECIFIED"
    INFO = "INCIDENT_SEVERITY_INFO"
    WARNING = "INCIDENT_SEVERITY_WARNING"
    CRITICAL = "INCIDENT_SEVERITY_CRITICAL"


class IncidentStatus(str, Enum):
    UNSPECIFIED = "INCIDENT_STATUS_UNSPECIFIED"
    OPEN = "INCIDENT_STATUS_OPEN"
    ACKNOWLEDGED = "INCIDENT_STATUS_ACKNOWLEDGED"
    RESOLVED = "INCIDENT_STATUS_RESOLVED"


# Fleet vehicle IDs: VH- followed by 4–8 digits (e.g. VH-0001234).
VEHICLE_ID_PATTERN = r"^VH-[0-9]{4,8}$"


class TelemetryEvent(BaseModel):
    """In-process validation mirror of argus.v1.TelemetryEvent."""

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


class IncidentEvent(BaseModel):
    """In-process validation mirror of argus.v1.IncidentEvent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    incident_id: str = Field(..., min_length=1)
    severity: IncidentSeverity
    source_service: str = Field(..., min_length=1)
    metric_name: str = Field(..., min_length=1)
    threshold: float
    observed_value: float
    timestamp: datetime
    status: IncidentStatus

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> object:
        if value is None or value == "":
            raise ValueError("timestamp is required")
        return value

    @model_validator(mode="after")
    def _reject_unspecified_enums(self) -> Self:
        if self.severity == IncidentSeverity.UNSPECIFIED:
            raise ValueError("severity must not be UNSPECIFIED")
        if self.status == IncidentStatus.UNSPECIFIED:
            raise ValueError("status must not be UNSPECIFIED")
        return self
