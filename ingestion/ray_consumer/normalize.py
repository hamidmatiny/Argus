"""Lightweight TelemetryEvent normalization for the Ray ingestion path."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ingestion.simulator.avro_codec import decode_confluent_avro, load_avro_schema

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


def normalize_record(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """
    Normalize a TelemetryEvent-shaped dict.

    Returns (normalized_record | None, issues).
    None means the record should be quarantined / dropped (not republished).
    """
    issues: list[str] = []
    out: dict[str, Any] = dict(raw)

    vehicle_id = str(out.get("vehicle_id") or "").strip()
    if not vehicle_id or not vehicle_id.startswith("VH-"):
        issues.append("invalid_vehicle_id")
        return None, issues
    out["vehicle_id"] = vehicle_id

    trip_id = str(out.get("trip_id") or "").strip()
    if not trip_id:
        issues.append("missing_trip_id")
        trip_id = "unknown"
    out["trip_id"] = trip_id

    ts = out.get("timestamp")
    if ts is None or ts == "":
        issues.append("missing_timestamp")
        return None, issues
    try:
        if isinstance(ts, datetime):
            parsed = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        out["timestamp"] = parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        issues.append("invalid_timestamp")
        return None, issues

    try:
        lat = float(out.get("gps_lat"))
        lon = float(out.get("gps_lon"))
    except (TypeError, ValueError):
        issues.append("malformed_gps")
        return None, issues
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        issues.append("gps_out_of_range")
        return None, issues
    out["gps_lat"] = lat
    out["gps_lon"] = lon

    try:
        speed = float(out.get("speed_mph"))
    except (TypeError, ValueError):
        issues.append("invalid_speed")
        return None, issues
    if speed < 0 or speed > 120:
        issues.append("speed_out_of_range")
        # Soft-clamp for recoverable spikes so Flink still sees a typed event.
        speed = max(0.0, min(120.0, speed))
        out["_clamped_speed"] = True
    out["speed_mph"] = speed

    for field, default in (
        ("brake_pressure", 0.0),
        ("lidar_temp_c", 0.0),
        ("compute_load_pct", 0.0),
    ):
        try:
            out[field] = float(out.get(field, default))
        except (TypeError, ValueError):
            issues.append(f"invalid_{field}")
            out[field] = default
    out["compute_load_pct"] = max(0.0, min(100.0, float(out["compute_load_pct"])))
    out["brake_pressure"] = max(0.0, float(out["brake_pressure"]))

    sensor = str(out.get("sensor_status") or "SENSOR_STATUS_UNSPECIFIED")
    if sensor not in _VALID_SENSOR:
        issues.append("invalid_sensor_status")
        sensor = "SENSOR_STATUS_DEGRADED"
    out["sensor_status"] = sensor

    device = str(out.get("device_type") or "DEVICE_TYPE_UNSPECIFIED")
    if device not in _VALID_DEVICE:
        issues.append("invalid_device_type")
        device = "DEVICE_TYPE_SIMULATOR"
    out["device_type"] = device

    hw = str(out.get("hardware_version") or "").strip()
    if not hw:
        issues.append("missing_hardware_version")
        hw = "unknown"
    out["hardware_version"] = hw

    # Strip internal markers before publish.
    out.pop("_clamped_speed", None)
    return out, issues


def decode_kafka_value(value: bytes) -> tuple[dict[str, Any] | None, str]:
    """
    Decode a Kafka value as Confluent-Avro or JSON.

    Returns (record | None, codec) where codec is avro|json|raw.
    """
    schema = load_avro_schema()
    try:
        _, record = decode_confluent_avro(value, schema=schema)
        return record, "avro"
    except Exception:
        pass

    try:
        import json

        record = json.loads(value.decode("utf-8"))
        if isinstance(record, dict):
            return record, "json"
    except Exception:
        pass

    return None, "raw"
