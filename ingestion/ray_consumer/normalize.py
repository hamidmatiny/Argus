"""Pass-through TelemetryEvent normalization for the Ray ingestion path.

Division of responsibility:
  - ray_consumer: decode + unambiguous type coercion only; publish structural
    failures to ``telemetry.quarantine``.
  - stream-processor: sole authority on semantic pass/fail (ranges, enums, regex).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ingestion.simulator.avro_codec import decode_confluent_avro, load_avro_schema


def normalize_record(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """
    Decode/coerce a TelemetryEvent-shaped dict without semantic laundering.

    Returns ``(normalized_record | None, structural_issues)``.
    ``None`` means a *structural* failure — publish to quarantine, do not
    republish to ``telemetry.normalized``.

    Out-of-range numerics and unrecognized enums are passed through unchanged
    so stream-processor (and later drift-monitor) see the real anomaly signal.
    """
    issues: list[str] = []
    out: dict[str, Any] = dict(raw)

    vehicle_id = out.get("vehicle_id")
    if vehicle_id is None or str(vehicle_id).strip() == "":
        issues.append("empty_vehicle_id")
        return None, issues
    out["vehicle_id"] = str(vehicle_id).strip()

    # trip_id / hardware_version / enums: pass through as-is (no defaults).
    if "trip_id" in out and out["trip_id"] is not None:
        out["trip_id"] = str(out["trip_id"])
    if "hardware_version" in out and out["hardware_version"] is not None:
        out["hardware_version"] = str(out["hardware_version"])
    if "sensor_status" in out and out["sensor_status"] is not None:
        out["sensor_status"] = str(out["sensor_status"])
    if "device_type" in out and out["device_type"] is not None:
        out["device_type"] = str(out["device_type"])

    ts = out.get("timestamp")
    if ts is None or ts == "":
        issues.append("unparseable_timestamp")
        return None, issues
    try:
        if isinstance(ts, datetime):
            parsed = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        out["timestamp"] = parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        issues.append("unparseable_timestamp")
        return None, issues

    try:
        out["gps_lat"] = float(out.get("gps_lat"))
        out["gps_lon"] = float(out.get("gps_lon"))
    except (TypeError, ValueError):
        issues.append("non_numeric_gps")
        return None, issues
    # Out-of-range GPS is a semantic issue — pass through for stream-processor.

    try:
        out["speed_mph"] = float(out.get("speed_mph"))
    except (TypeError, ValueError):
        issues.append("non_numeric_speed")
        return None, issues
    # Out-of-range speed is a semantic issue — pass through (no clamping).

    for field in ("brake_pressure", "lidar_temp_c", "compute_load_pct"):
        if field not in out:
            continue
        raw_val = out.get(field)
        if raw_val is None or raw_val == "":
            # Leave as-is / missing for stream-processor; do not invent defaults.
            continue
        try:
            out[field] = float(raw_val)
        except (TypeError, ValueError):
            # Non-numeric optional metric: leave original value for QA to reject.
            pass

    return out, issues


def build_structural_quarantine(
    record: dict[str, Any] | None,
    issues: list[str],
    *,
    source_topic: str = "telemetry.raw",
) -> dict[str, Any]:
    """
    Structured DLQ payload matching stream-processor's quarantine schema.

    Fields: rejected_at, source_topic, vehicle_id, field, rule, reason,
    violations, raw_payload — same shape as
    ``stream_processor.validation.rules.build_quarantine_record``.
    """
    issue = issues[0] if issues else "structural_failure"
    field_map = {
        "empty_vehicle_id": ("vehicle_id", "required_nonempty", "vehicle_id is empty"),
        "unparseable_timestamp": ("timestamp", "iso8601", "timestamp is missing or unparseable"),
        "non_numeric_gps": ("gps_lat", "type:float", "gps_lat/gps_lon must be numeric"),
        "non_numeric_speed": ("speed_mph", "type:float", "speed_mph must be numeric"),
        "decode_failed": ("_payload", "decode", "kafka value could not be decoded"),
        "avro_encode_failed": ("_payload", "avro_encode", "normalized record not Avro-encodable"),
    }
    field, rule, reason = field_map.get(
        issue, ("_payload", issue, f"structural failure: {issue}")
    )
    violations = [
        {"field": field, "rule": rule, "message": reason}
        for issue in issues
        for field, rule, reason in [
            field_map.get(issue, ("_payload", issue, f"structural failure: {issue}"))
        ]
    ]
    return {
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "source_topic": source_topic,
        "vehicle_id": (record or {}).get("vehicle_id"),
        "field": field,
        "rule": rule,
        "reason": reason,
        "violations": violations,
        "raw_payload": record,
    }


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
