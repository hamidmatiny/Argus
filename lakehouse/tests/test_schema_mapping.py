"""Unit tests for TelemetryEvent / quarantine → Iceberg row mapping."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from common.schema import (
    map_quarantine_record,
    map_telemetry_record,
    parse_event_timestamp,
    partition_keys_for_telemetry,
    quarantine_rows_to_arrow,
    telemetry_rows_to_arrow,
)


def _sample_telemetry(**overrides):
    base = {
        "vehicle_id": "VH-0000001",
        "trip_id": "trip-abc",
        "timestamp": "2026-07-22T15:30:00+00:00",
        "gps_lat": 40.44,
        "gps_lon": -79.99,
        "speed_mph": 32.5,
        "brake_pressure": 0.21,
        "lidar_temp_c": 41.2,
        "compute_load_pct": 48.0,
        "sensor_status": "SENSOR_STATUS_OK",
        "hardware_version": "hw-rev-3.2",
        "device_type": "DEVICE_TYPE_SIMULATOR",
    }
    base.update(overrides)
    return base


def test_parse_event_timestamp_iso_and_epoch():
    iso = parse_event_timestamp("2026-07-22T12:00:00Z")
    assert iso == datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)

    epoch = parse_event_timestamp(1_721_649_600)  # 2024-07-22T12:00:00Z approx
    assert epoch.tzinfo is not None


def test_map_telemetry_record_preserves_fields():
    row = map_telemetry_record(_sample_telemetry())
    assert row["vehicle_id"] == "VH-0000001"
    assert row["speed_mph"] == 32.5
    assert row["device_type"] == "DEVICE_TYPE_SIMULATOR"
    assert row["timestamp"].date() == date(2026, 7, 22)


def test_map_telemetry_missing_field_raises():
    bad = _sample_telemetry()
    del bad["speed_mph"]
    with pytest.raises(KeyError):
        map_telemetry_record(bad)


def test_partition_keys_device_type_and_day():
    keys = partition_keys_for_telemetry(_sample_telemetry())
    assert keys["device_type"] == "DEVICE_TYPE_SIMULATOR"
    assert keys["event_day"] == date(2026, 7, 22)

    keys2 = partition_keys_for_telemetry(
        _sample_telemetry(timestamp="2026-01-05T23:59:59Z")
    )
    assert keys2["event_day"] == date(2026, 1, 5)


def test_map_quarantine_record_serializes_nested():
    q = {
        "rejected_at": "2026-07-22T16:00:00Z",
        "source_topic": "telemetry.normalized",
        "vehicle_id": "VH-0000002",
        "field": "gps_lat",
        "rule": "range",
        "reason": "out of bounds",
        "violations": [{"field": "gps_lat", "rule": "range", "message": "bad"}],
        "raw_payload": {"vehicle_id": "VH-0000002", "gps_lat": 999.0},
    }
    row = map_quarantine_record(q)
    assert row["source_topic"] == "telemetry.normalized"
    assert '"gps_lat"' in row["violations_json"]
    assert "999" in row["raw_payload_json"]


def test_arrow_roundtrip_shapes():
    rows = [map_telemetry_record(_sample_telemetry())]
    table = telemetry_rows_to_arrow(rows)
    assert table.num_rows == 1
    assert "device_type" in table.column_names
    assert table.schema.field("timestamp").type.tz == "UTC"

    qrows = [
        map_quarantine_record(
            {
                "rejected_at": "2026-07-22T16:00:00Z",
                "source_topic": "telemetry.normalized",
                "violations": [],
                "raw_payload": {},
            }
        )
    ]
    qtable = quarantine_rows_to_arrow(qrows)
    assert qtable.num_rows == 1
