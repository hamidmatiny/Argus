"""Engine-agnostic TelemetryEvent QA rules (mirrors shared/ Pandera contract)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Keep in sync with shared/contracts/v1/models.py + pandera_schemas.py
VEHICLE_ID_PATTERN = re.compile(r"^VH-[0-9]{4,8}$")
_VALID_SENSOR = {
    "SENSOR_STATUS_OK",
    "SENSOR_STATUS_DEGRADED",
    "SENSOR_STATUS_FAULT",
}
_VALID_DEVICE = {
    "DEVICE_TYPE_VEHICLE",
    "DEVICE_TYPE_EDGE_GATEWAY",
    "DEVICE_TYPE_SIMULATOR",
}


@dataclass(frozen=True)
class Violation:
    field: str
    rule: str
    message: str


@dataclass
class ValidationResult:
    ok: bool
    violations: list[Violation] = field(default_factory=list)

    @property
    def primary(self) -> Violation | None:
        return self.violations[0] if self.violations else None


def validate_telemetry_event(record: dict[str, Any] | None) -> ValidationResult:
    """
    Row-level contract checks equivalent to TELEMETRY_EVENT_SCHEMA.

    Safe to call from Flink ProcessFunctions and the local runner.
    """
    if not isinstance(record, dict):
        return ValidationResult(
            ok=False,
            violations=[
                Violation(
                    field="_payload",
                    rule="required_object",
                    message="record must be a JSON/Avro object",
                )
            ],
        )

    violations: list[Violation] = []

    vehicle_id = record.get("vehicle_id")
    if not isinstance(vehicle_id, str) or not VEHICLE_ID_PATTERN.match(vehicle_id):
        violations.append(
            Violation(
                field="vehicle_id",
                rule="regex:^VH-[0-9]{4,8}$",
                message=f"invalid vehicle_id: {vehicle_id!r}",
            )
        )

    trip_id = record.get("trip_id")
    if not isinstance(trip_id, str) or len(trip_id.strip()) < 1:
        violations.append(
            Violation(
                field="trip_id",
                rule="required_nonempty",
                message="trip_id is required",
            )
        )

    ts = record.get("timestamp")
    if ts is None or ts == "":
        violations.append(
            Violation(
                field="timestamp",
                rule="required",
                message="timestamp is required",
            )
        )
    else:
        try:
            if isinstance(ts, datetime):
                _ = ts
            else:
                datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            violations.append(
                Violation(
                    field="timestamp",
                    rule="iso8601",
                    message=f"timestamp not ISO-8601: {ts!r}",
                )
            )

    for field_name, lo, hi in (
        ("gps_lat", -90.0, 90.0),
        ("gps_lon", -180.0, 180.0),
        ("speed_mph", 0.0, 120.0),
        ("compute_load_pct", 0.0, 100.0),
    ):
        raw = record.get(field_name)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            violations.append(
                Violation(
                    field=field_name,
                    rule="type:float",
                    message=f"{field_name} must be numeric, got {raw!r}",
                )
            )
            continue
        if value < lo or value > hi:
            violations.append(
                Violation(
                    field=field_name,
                    rule=f"in_range[{lo},{hi}]",
                    message=f"{field_name}={value} outside [{lo}, {hi}]",
                )
            )

    try:
        brake = float(record.get("brake_pressure"))
        if brake < 0.0:
            violations.append(
                Violation(
                    field="brake_pressure",
                    rule="ge:0",
                    message=f"brake_pressure={brake} must be >= 0",
                )
            )
    except (TypeError, ValueError):
        violations.append(
            Violation(
                field="brake_pressure",
                rule="type:float",
                message=f"brake_pressure must be numeric, got {record.get('brake_pressure')!r}",
            )
        )

    try:
        float(record.get("lidar_temp_c"))
    except (TypeError, ValueError):
        violations.append(
            Violation(
                field="lidar_temp_c",
                rule="type:float",
                message=f"lidar_temp_c must be numeric, got {record.get('lidar_temp_c')!r}",
            )
        )

    sensor = record.get("sensor_status")
    if sensor not in _VALID_SENSOR:
        violations.append(
            Violation(
                field="sensor_status",
                rule="enum:SensorStatus",
                message=f"invalid sensor_status: {sensor!r}",
            )
        )

    device = record.get("device_type")
    if device not in _VALID_DEVICE:
        violations.append(
            Violation(
                field="device_type",
                rule="enum:DeviceType",
                message=f"invalid device_type: {device!r}",
            )
        )

    hw = record.get("hardware_version")
    if not isinstance(hw, str) or len(hw.strip()) < 1:
        violations.append(
            Violation(
                field="hardware_version",
                rule="required_nonempty",
                message="hardware_version is required",
            )
        )

    return ValidationResult(ok=len(violations) == 0, violations=violations)


def build_quarantine_record(
    record: dict[str, Any] | None,
    result: ValidationResult,
    *,
    source_topic: str = "telemetry.normalized",
) -> dict[str, Any]:
    """Structured DLQ payload: field, rule, raw payload."""
    primary = result.primary
    return {
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "source_topic": source_topic,
        "vehicle_id": (record or {}).get("vehicle_id"),
        "field": primary.field if primary else "_unknown",
        "rule": primary.rule if primary else "_unknown",
        "reason": primary.message if primary else "validation_failed",
        "violations": [
            {"field": v.field, "rule": v.rule, "message": v.message}
            for v in result.violations
        ],
        "raw_payload": record,
    }
