"""Tests for tumbling quarantine-rate windows + Flink map_validation."""

from __future__ import annotations

import json

from flink_job.job import QuarantineRateAggregator, map_validation
from local_runner.runner import process_record
from validation.metrics import TumblingQuarantineWindow, compute_quarantine_rate


def test_compute_quarantine_rate():
    assert compute_quarantine_rate(0, 0) == 0.0
    assert compute_quarantine_rate(10, 2) == 0.2


def test_tumbling_window_emits_on_close():
    w = TumblingQuarantineWindow(window_size=4, threshold=0.15)
    assert w.observe("VH-1", False) is None
    assert w.observe("VH-1", False) is None
    assert w.observe("VH-1", True) is None
    metric = w.observe("VH-1", True)
    assert metric is not None
    assert metric.total == 4
    assert metric.quarantined == 2
    assert metric.quarantine_rate == 0.5
    assert metric.exceeded is True


def test_process_record_routes_valid_and_invalid():
    windows = TumblingQuarantineWindow(window_size=100)
    good = {
        "vehicle_id": "VH-0000001",
        "trip_id": "t",
        "timestamp": "2026-07-22T18:00:00Z",
        "gps_lat": 1.0,
        "gps_lon": 2.0,
        "speed_mph": 10.0,
        "brake_pressure": 0.0,
        "lidar_temp_c": 20.0,
        "compute_load_pct": 10.0,
        "sensor_status": "SENSOR_STATUS_OK",
        "hardware_version": "hw-1",
        "device_type": "DEVICE_TYPE_VEHICLE",
    }
    out = process_record(good, windows=windows)
    assert out["route"] == "validated"

    bad = dict(good, gps_lat=999.0)
    out = process_record(bad, windows=windows)
    assert out["route"] == "quarantine"
    assert out["payload"]["field"] == "gps_lat"


def test_flink_map_validation_both_routes():
    good = {
        "vehicle_id": "VH-0000002",
        "trip_id": "t",
        "timestamp": "2026-07-22T18:00:00Z",
        "gps_lat": 1.0,
        "gps_lon": 2.0,
        "speed_mph": 10.0,
        "brake_pressure": 0.0,
        "lidar_temp_c": 20.0,
        "compute_load_pct": 10.0,
        "sensor_status": "SENSOR_STATUS_OK",
        "hardware_version": "hw-1",
        "device_type": "DEVICE_TYPE_VEHICLE",
    }
    route, payload = map_validation(json.dumps(good))
    assert route == "validated"
    assert json.loads(payload)["vehicle_id"] == "VH-0000002"

    route, payload = map_validation(json.dumps({**good, "speed_mph": 999}))
    assert route == "quarantine"
    body = json.loads(payload)
    assert body["field"] == "speed_mph"
    assert "raw_payload" in body


def test_flink_aggregator_emits_metric():
    agg = QuarantineRateAggregator(window_size=3, threshold=0.15)
    assert agg.add("VH-1", True) is None
    assert agg.add("VH-1", False) is None
    metric = agg.add("VH-1", True)
    assert metric is not None
    assert metric["quarantined"] == 2
    assert metric["exceeded"] is True
