"""Iceberg table schemas and TelemetryEvent / quarantine → row mapping."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform, IdentityTransform
from pyiceberg.types import (
    DoubleType,
    NestedField,
    StringType,
    TimestamptzType,
)

# Stable field ids — partition transforms reference these.
TELEMETRY_SCHEMA = Schema(
    NestedField(1, "vehicle_id", StringType(), required=True),
    NestedField(2, "trip_id", StringType(), required=True),
    NestedField(3, "timestamp", TimestamptzType(), required=True),
    NestedField(4, "gps_lat", DoubleType(), required=True),
    NestedField(5, "gps_lon", DoubleType(), required=True),
    NestedField(6, "speed_mph", DoubleType(), required=True),
    NestedField(7, "brake_pressure", DoubleType(), required=True),
    NestedField(8, "lidar_temp_c", DoubleType(), required=True),
    NestedField(9, "compute_load_pct", DoubleType(), required=True),
    NestedField(10, "sensor_status", StringType(), required=True),
    NestedField(11, "hardware_version", StringType(), required=True),
    NestedField(12, "device_type", StringType(), required=True),
)

# Partition by device_type (identity) + day(timestamp) — Hive-style layout under
# Iceberg, matching hydra-data-factory's device_type partition continuity while
# adding day for time-bounded scans.
TELEMETRY_PARTITION_SPEC = PartitionSpec(
    PartitionField(
        source_id=12,
        field_id=1000,
        transform=IdentityTransform(),
        name="device_type",
    ),
    PartitionField(
        source_id=3,
        field_id=1001,
        transform=DayTransform(),
        name="event_day",
    ),
)

QUARANTINE_SCHEMA = Schema(
    NestedField(1, "rejected_at", TimestamptzType(), required=True),
    NestedField(2, "source_topic", StringType(), required=True),
    NestedField(3, "vehicle_id", StringType(), required=False),
    NestedField(4, "field", StringType(), required=False),
    NestedField(5, "rule", StringType(), required=False),
    NestedField(6, "reason", StringType(), required=False),
    NestedField(7, "violations_json", StringType(), required=True),
    NestedField(8, "raw_payload_json", StringType(), required=True),
)

QUARANTINE_PARTITION_SPEC = PartitionSpec(
    PartitionField(
        source_id=1,
        field_id=1000,
        transform=DayTransform(),
        name="reject_day",
    ),
)


def parse_event_timestamp(value: Any) -> datetime:
    """Parse TelemetryEvent timestamp (ISO-8601 string or datetime) to UTC."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        # Hydra-compatible: unix seconds / millis.
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    else:
        raise TypeError(f"unsupported timestamp type: {type(value)!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def partition_keys_for_telemetry(record: dict[str, Any]) -> dict[str, Any]:
    """
    Derive logical partition keys used by Iceberg transforms.

    Returns device_type (identity) and event_day (date) for assertions / docs.
    """
    ts = parse_event_timestamp(record["timestamp"])
    return {
        "device_type": str(record.get("device_type") or "DEVICE_TYPE_UNSPECIFIED"),
        "event_day": date(ts.year, ts.month, ts.day),
    }


def map_telemetry_record(record: dict[str, Any]) -> dict[str, Any]:
    """Map a validated TelemetryEvent dict to an Iceberg row."""
    required = (
        "vehicle_id",
        "trip_id",
        "timestamp",
        "gps_lat",
        "gps_lon",
        "speed_mph",
        "brake_pressure",
        "lidar_temp_c",
        "compute_load_pct",
        "sensor_status",
        "hardware_version",
        "device_type",
    )
    missing = [k for k in required if k not in record]
    if missing:
        raise KeyError(f"telemetry record missing fields: {missing}")

    return {
        "vehicle_id": str(record["vehicle_id"]),
        "trip_id": str(record["trip_id"]),
        "timestamp": parse_event_timestamp(record["timestamp"]),
        "gps_lat": float(record["gps_lat"]),
        "gps_lon": float(record["gps_lon"]),
        "speed_mph": float(record["speed_mph"]),
        "brake_pressure": float(record["brake_pressure"]),
        "lidar_temp_c": float(record["lidar_temp_c"]),
        "compute_load_pct": float(record["compute_load_pct"]),
        "sensor_status": str(record["sensor_status"]),
        "hardware_version": str(record["hardware_version"]),
        "device_type": str(record["device_type"]),
    }


def map_quarantine_record(record: dict[str, Any]) -> dict[str, Any]:
    """Map a Phase-3 quarantine JSON dict to an Iceberg row."""
    rejected_raw = record.get("rejected_at") or datetime.now(timezone.utc).isoformat()
    return {
        "rejected_at": parse_event_timestamp(rejected_raw),
        "source_topic": str(record.get("source_topic") or ""),
        "vehicle_id": (
            str(record["vehicle_id"]) if record.get("vehicle_id") is not None else None
        ),
        "field": str(record["field"]) if record.get("field") is not None else None,
        "rule": str(record["rule"]) if record.get("rule") is not None else None,
        "reason": str(record["reason"]) if record.get("reason") is not None else None,
        "violations_json": json.dumps(record.get("violations") or [], default=str),
        "raw_payload_json": json.dumps(record.get("raw_payload") or {}, default=str),
    }


def _telemetry_arrow_schema():
    import pyarrow as pa

    return pa.schema(
        [
            pa.field("vehicle_id", pa.string(), nullable=False),
            pa.field("trip_id", pa.string(), nullable=False),
            pa.field("timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("gps_lat", pa.float64(), nullable=False),
            pa.field("gps_lon", pa.float64(), nullable=False),
            pa.field("speed_mph", pa.float64(), nullable=False),
            pa.field("brake_pressure", pa.float64(), nullable=False),
            pa.field("lidar_temp_c", pa.float64(), nullable=False),
            pa.field("compute_load_pct", pa.float64(), nullable=False),
            pa.field("sensor_status", pa.string(), nullable=False),
            pa.field("hardware_version", pa.string(), nullable=False),
            pa.field("device_type", pa.string(), nullable=False),
        ]
    )


def _quarantine_arrow_schema():
    import pyarrow as pa

    return pa.schema(
        [
            pa.field("rejected_at", pa.timestamp("us", tz="UTC"), nullable=False),
            pa.field("source_topic", pa.string(), nullable=False),
            pa.field("vehicle_id", pa.string(), nullable=True),
            pa.field("field", pa.string(), nullable=True),
            pa.field("rule", pa.string(), nullable=True),
            pa.field("reason", pa.string(), nullable=True),
            pa.field("violations_json", pa.string(), nullable=False),
            pa.field("raw_payload_json", pa.string(), nullable=False),
        ]
    )


def telemetry_rows_to_arrow(rows: list[dict[str, Any]]):
    """Convert mapped telemetry rows to a PyArrow Table (Snappy write later)."""
    import pyarrow as pa

    schema = _telemetry_arrow_schema()
    if not rows:
        return pa.Table.from_pylist([], schema=schema)

    return pa.Table.from_pylist(
        [
            {
                "vehicle_id": r["vehicle_id"],
                "trip_id": r["trip_id"],
                "timestamp": r["timestamp"],
                "gps_lat": r["gps_lat"],
                "gps_lon": r["gps_lon"],
                "speed_mph": r["speed_mph"],
                "brake_pressure": r["brake_pressure"],
                "lidar_temp_c": r["lidar_temp_c"],
                "compute_load_pct": r["compute_load_pct"],
                "sensor_status": r["sensor_status"],
                "hardware_version": r["hardware_version"],
                "device_type": r["device_type"],
            }
            for r in rows
        ],
        schema=schema,
    )


def quarantine_rows_to_arrow(rows: list[dict[str, Any]]):
    """Convert mapped quarantine rows to a PyArrow Table."""
    import pyarrow as pa

    schema = _quarantine_arrow_schema()
    if not rows:
        return pa.Table.from_pylist([], schema=schema)

    return pa.Table.from_pylist(
        [
            {
                "rejected_at": r["rejected_at"],
                "source_topic": r["source_topic"],
                "vehicle_id": r["vehicle_id"],
                "field": r["field"],
                "rule": r["rule"],
                "reason": r["reason"],
                "violations_json": r["violations_json"],
                "raw_payload_json": r["raw_payload_json"],
            }
            for r in rows
        ],
        schema=schema,
    )
