"""Unit tests for QA validation rules (engine-agnostic)."""

from __future__ import annotations

from validation.rules import build_quarantine_record, validate_telemetry_event


def _good(**overrides):
    base = {
        "vehicle_id": "VH-0000001",
        "trip_id": "trip-1",
        "timestamp": "2026-07-22T18:00:00Z",
        "gps_lat": 40.44,
        "gps_lon": -80.0,
        "speed_mph": 35.0,
        "brake_pressure": 0.1,
        "lidar_temp_c": 40.0,
        "compute_load_pct": 50.0,
        "sensor_status": "SENSOR_STATUS_OK",
        "hardware_version": "hw-rev-3.2",
        "device_type": "DEVICE_TYPE_SIMULATOR",
    }
    base.update(overrides)
    return base


def test_accepts_valid_event():
    result = validate_telemetry_event(_good())
    assert result.ok
    assert result.violations == []


def test_rejects_bad_vehicle_id():
    result = validate_telemetry_event(_good(vehicle_id="NOPE"))
    assert not result.ok
    assert any(v.field == "vehicle_id" for v in result.violations)


def test_rejects_gps_out_of_range():
    result = validate_telemetry_event(_good(gps_lat=999.0))
    assert not result.ok
    assert any(v.field == "gps_lat" and "in_range" in v.rule for v in result.violations)


def test_rejects_speed_out_of_range():
    result = validate_telemetry_event(_good(speed_mph=200.0))
    assert not result.ok
    assert any(v.field == "speed_mph" for v in result.violations)


def test_rejects_missing_timestamp():
    result = validate_telemetry_event(_good(timestamp=""))
    assert not result.ok
    assert any(v.field == "timestamp" for v in result.violations)


def test_quarantine_record_structure():
    record = _good(speed_mph=-1.0)
    result = validate_telemetry_event(record)
    q = build_quarantine_record(record, result)
    assert q["field"] == "speed_mph"
    assert "rule" in q and "reason" in q
    assert q["raw_payload"]["vehicle_id"] == "VH-0000001"
    assert isinstance(q["violations"], list) and q["violations"]
