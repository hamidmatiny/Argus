"""Tests for Ray consumer pass-through normalization."""

from __future__ import annotations

import pytest
import ray

from ingestion.ray_consumer.normalize import (
    build_structural_quarantine,
    decode_kafka_value,
    normalize_record,
)
from ingestion.simulator.avro_codec import encode_confluent_avro, load_avro_schema


@pytest.fixture(scope="module")
def ray_local():
    """Initialize a tiny local Ray instance (no external cluster) for CI."""
    if ray.is_initialized():
        ray.shutdown()
    ray.init(
        num_cpus=2,
        include_dashboard=False,
        ignore_reinit_error=True,
        logging_level="ERROR",
    )
    yield
    ray.shutdown()


def _valid_event(**overrides):
    base = {
        "vehicle_id": "VH-0000001",
        "trip_id": "trip-abc",
        "timestamp": "2026-07-22T15:00:00Z",
        "gps_lat": 37.77,
        "gps_lon": -122.42,
        "speed_mph": 42.0,
        "brake_pressure": 0.2,
        "lidar_temp_c": 31.0,
        "compute_load_pct": 55.0,
        "sensor_status": "SENSOR_STATUS_OK",
        "hardware_version": "hw-rev-3.2",
        "device_type": "DEVICE_TYPE_SIMULATOR",
    }
    base.update(overrides)
    return base


def test_normalize_accepts_valid_record():
    out, issues = normalize_record(_valid_event())
    assert out is not None
    assert out["vehicle_id"] == "VH-0000001"
    assert "Z" in out["timestamp"] or "+" in out["timestamp"]
    assert issues == []


def test_normalize_passes_through_out_of_range_gps():
    """Semantic GPS range is stream-processor's job — do not drop here."""
    out, issues = normalize_record(_valid_event(gps_lat=999.0, gps_lon=-999.0))
    assert out is not None
    assert out["gps_lat"] == 999.0
    assert out["gps_lon"] == -999.0
    assert issues == []


def test_normalize_rejects_non_numeric_gps():
    out, issues = normalize_record(_valid_event(gps_lat="not-a-number"))
    assert out is None
    assert "non_numeric_gps" in issues


def test_normalize_rejects_missing_timestamp():
    out, issues = normalize_record(_valid_event(timestamp=""))
    assert out is None
    assert "unparseable_timestamp" in issues


def test_normalize_passthrough_out_of_range_speed_and_bad_enum():
    """No clamping / no enum substitution — preserve anomaly signal."""
    out, issues = normalize_record(
        _valid_event(speed_mph=9999.0, sensor_status="SENSOR_STATUS_UNSPECIFIED")
    )
    assert out is not None
    assert out["speed_mph"] == 9999.0
    assert out["sensor_status"] == "SENSOR_STATUS_UNSPECIFIED"
    assert issues == []


def test_normalize_passthrough_empty_trip_and_hardware():
    out, issues = normalize_record(
        _valid_event(trip_id="", hardware_version="")
    )
    assert out is not None
    assert out["trip_id"] == ""
    assert out["hardware_version"] == ""


def test_normalize_rejects_empty_vehicle_id():
    out, issues = normalize_record(_valid_event(vehicle_id=""))
    assert out is None
    assert "empty_vehicle_id" in issues


def test_normalize_passthrough_non_vh_vehicle_id():
    """Regex vehicle_id checks belong to stream-processor."""
    out, issues = normalize_record(_valid_event(vehicle_id="NOPE-123"))
    assert out is not None
    assert out["vehicle_id"] == "NOPE-123"


def test_structural_quarantine_schema_matches_stream_processor():
    q = build_structural_quarantine(
        {"vehicle_id": "", "speed_mph": 1},
        ["empty_vehicle_id"],
        source_topic="telemetry.raw",
    )
    assert q["source_topic"] == "telemetry.raw"
    assert q["field"] == "vehicle_id"
    assert q["rule"] == "required_nonempty"
    assert "reason" in q and "violations" in q and "raw_payload" in q
    assert "rejected_at" in q


def test_decode_confluent_avro_roundtrip():
    schema = load_avro_schema()
    record = _valid_event()
    payload = encode_confluent_avro(record, schema=schema, schema_id=1)
    decoded, codec = decode_kafka_value(payload)
    assert codec == "avro"
    assert decoded is not None
    assert decoded["vehicle_id"] == record["vehicle_id"]


def test_decode_corrupt_json_returns_raw():
    decoded, codec = decode_kafka_value(b'{"vehicle_id": "VH-1"')
    assert decoded is None
    assert codec == "raw"


@ray.remote
class _EchoStreamer:
    def __init__(self, partition_id: str) -> None:
        self.partition_id = partition_id

    def process_batch(self, max_messages: int = 1) -> dict:
        return {"partition_id": self.partition_id, "ok": True, "n": max_messages}


def test_ray_local_actor_pool_fanout(ray_local):
    streamers = [_EchoStreamer.remote(f"p-{i}") for i in range(3)]
    futures = [s.process_batch.remote(5) for s in streamers]
    results = ray.get(futures)
    assert len(results) == 3
    assert {r["partition_id"] for r in results} == {"p-0", "p-1", "p-2"}
    assert all(r["ok"] for r in results)
