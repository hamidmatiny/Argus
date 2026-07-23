"""IngestClient validation tests (no live Kafka)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from argus_sdk import DeviceType, IngestClient, SensorStatus, TelemetryEvent


def _sample() -> TelemetryEvent:
    return TelemetryEvent(
        vehicle_id="VH-0001234",
        trip_id="trip-1",
        timestamp=datetime.now(tz=timezone.utc),
        gps_lat=37.7,
        gps_lon=-122.4,
        speed_mph=30.0,
        brake_pressure=1.0,
        lidar_temp_c=40.0,
        compute_load_pct=55.0,
        sensor_status=SensorStatus.OK,
        hardware_version="hw-1",
        device_type=DeviceType.SIMULATOR,
    )


def test_telemetry_event_rejects_bad_vehicle_id() -> None:
    with pytest.raises(Exception):
        TelemetryEvent(
            vehicle_id="BAD",
            trip_id="t",
            timestamp=datetime.now(tz=timezone.utc),
            gps_lat=0,
            gps_lon=0,
            speed_mph=0,
            brake_pressure=0,
            lidar_temp_c=0,
            compute_load_pct=0,
            sensor_status=SensorStatus.OK,
            hardware_version="h",
            device_type=DeviceType.VEHICLE,
        )


def test_ingest_requires_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "kafka", None)  # type: ignore[assignment]
    # If kafka is installed, skip this negative path.
    try:
        import kafka  # noqa: F401

        pytest.skip("kafka-python installed")
    except ImportError:
        with pytest.raises(ImportError, match="ingest"):
            IngestClient(schema_id=1)


def test_event_to_avro_record_shape() -> None:
    rec = _sample().to_avro_record()
    assert rec["vehicle_id"] == "VH-0001234"
    assert rec["sensor_status"] == "SENSOR_STATUS_OK"
    assert isinstance(rec["timestamp"], str)
