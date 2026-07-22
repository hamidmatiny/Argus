"""Iceberg partition spec + append via local sqlite catalog fixture."""

from __future__ import annotations

from common.schema import (
    TELEMETRY_PARTITION_SPEC,
    map_quarantine_record,
    map_telemetry_record,
    partition_keys_for_telemetry,
    quarantine_rows_to_arrow,
    telemetry_rows_to_arrow,
)
from common.sink import IcebergBatchSink


def test_telemetry_partition_spec_fields():
    names = {f.name for f in TELEMETRY_PARTITION_SPEC.fields}
    assert names == {"device_type", "event_day"}
    transforms = {f.name: f.transform.__class__.__name__ for f in TELEMETRY_PARTITION_SPEC.fields}
    assert transforms["device_type"] == "IdentityTransform"
    assert transforms["event_day"] == "DayTransform"


def test_append_telemetry_to_sqlite_catalog(telemetry_table):
    rows = [
        map_telemetry_record(
            {
                "vehicle_id": "VH-0000001",
                "trip_id": "t1",
                "timestamp": "2026-07-22T10:00:00Z",
                "gps_lat": 40.0,
                "gps_lon": -80.0,
                "speed_mph": 20.0,
                "brake_pressure": 0.1,
                "lidar_temp_c": 40.0,
                "compute_load_pct": 30.0,
                "sensor_status": "SENSOR_STATUS_OK",
                "hardware_version": "hw-rev-3.2",
                "device_type": "DEVICE_TYPE_SIMULATOR",
            }
        ),
        map_telemetry_record(
            {
                "vehicle_id": "VH-0000002",
                "trip_id": "t2",
                "timestamp": "2026-07-23T11:00:00Z",
                "gps_lat": 41.0,
                "gps_lon": -81.0,
                "speed_mph": 25.0,
                "brake_pressure": 0.2,
                "lidar_temp_c": 39.0,
                "compute_load_pct": 35.0,
                "sensor_status": "SENSOR_STATUS_OK",
                "hardware_version": "hw-rev-3.3",
                "device_type": "DEVICE_TYPE_VEHICLE",
            }
        ),
    ]
    sink = IcebergBatchSink(
        telemetry_table,
        to_arrow=telemetry_rows_to_arrow,
        batch_size=10,
        flush_interval_sec=60.0,
    )
    for row in rows:
        sink.add(row)
    sink.flush()
    assert sink.rows_appended == 2

    scan = telemetry_table.scan().to_arrow()
    assert scan.num_rows == 2
    device_types = set(scan.column("device_type").to_pylist())
    assert device_types == {"DEVICE_TYPE_SIMULATOR", "DEVICE_TYPE_VEHICLE"}

    # Partition keys derived from the same mapping the writer uses.
    keys = [partition_keys_for_telemetry({
        "timestamp": r["timestamp"].isoformat(),
        "device_type": r["device_type"],
    }) for r in rows]
    assert {k["device_type"] for k in keys} == device_types


def test_append_quarantine_to_sqlite_catalog(quarantine_table):
    rows = [
        map_quarantine_record(
            {
                "rejected_at": "2026-07-22T12:00:00Z",
                "source_topic": "telemetry.normalized",
                "vehicle_id": "VH-0000009",
                "field": "speed_mph",
                "rule": "range",
                "reason": "too fast",
                "violations": [{"field": "speed_mph", "rule": "range", "message": ">120"}],
                "raw_payload": {"speed_mph": 999},
            }
        )
    ]
    sink = IcebergBatchSink(
        quarantine_table,
        to_arrow=quarantine_rows_to_arrow,
        batch_size=1,
        flush_interval_sec=60.0,
    )
    sink.add(rows[0])
    assert sink.rows_appended == 1
    scanned = quarantine_table.scan().to_arrow()
    assert scanned.num_rows == 1
    assert scanned.column("source_topic")[0].as_py() == "telemetry.normalized"
