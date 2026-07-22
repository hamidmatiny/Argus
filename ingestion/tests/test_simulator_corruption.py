"""Tests for simulator corruption / anomaly injection."""

from __future__ import annotations

import random

from ingestion.simulator.anomalies import (
    CORRUPTION_STRATEGIES,
    corrupt_payload,
    maybe_runtime_anomaly,
    memory_leak_bytes,
)
from ingestion.simulator.generator import VehicleTelemetrySimulator, default_vehicle_ids


def _clean_payload() -> dict:
    return {
        "vehicle_id": "VH-0000001",
        "trip_id": "trip-1",
        "timestamp": "2026-07-22T12:00:00+00:00",
        "gps_lat": 40.44,
        "gps_lon": -80.0,
        "speed_mph": 30.0,
        "brake_pressure": 0.1,
        "lidar_temp_c": 40.0,
        "compute_load_pct": 50.0,
        "sensor_status": "SENSOR_STATUS_OK",
        "hardware_version": "hw-rev-3.2",
        "device_type": "DEVICE_TYPE_SIMULATOR",
    }


def test_default_vehicle_ids_match_contract_pattern():
    ids = default_vehicle_ids(3)
    assert ids == ["VH-0000001", "VH-0000002", "VH-0000003"]


def test_corrupt_payload_covers_all_strategies():
    seen: set[str] = set()
    rng = random.Random(0)
    for _ in range(200):
        payload, strategy, raw = corrupt_payload(
            _clean_payload(), rng=rng, vehicle_id="VH-0000001"
        )
        seen.add(strategy)
        if strategy == "corrupt_json":
            assert payload is None
            assert raw is not None
            assert b"{" in raw or b"vehicle" in raw
        else:
            assert payload is not None
            assert raw is None
            if strategy == "malformed_gps":
                assert abs(payload["gps_lat"]) > 90 or abs(payload["gps_lon"]) > 180
            if strategy == "invalid_speed":
                assert payload["speed_mph"] > 120
            if strategy == "null_timestamp":
                assert payload["timestamp"] == ""
            if strategy == "drop_vehicle_id":
                assert payload["vehicle_id"] == ""
            if strategy == "missing_fields":
                assert payload["hardware_version"] == ""
    assert seen == set(CORRUPTION_STRATEGIES)


def test_simulator_injects_corruption_at_failure_rate():
    sim = VehicleTelemetrySimulator(
        vehicle_ids=default_vehicle_ids(2),
        failure_rate=1.0,
        seed=42,
    )
    corrupted = 0
    for _ in range(20):
        record, strategy, raw = sim.next_message()
        if strategy is not None or raw is not None:
            corrupted += 1
    assert corrupted == 20
    assert sim.stats["corrupted"] == 20


def test_simulator_clean_when_failure_rate_zero():
    sim = VehicleTelemetrySimulator(
        vehicle_ids=default_vehicle_ids(1),
        failure_rate=0.0,
        seed=1,
    )
    for _ in range(10):
        record, strategy, raw = sim.next_message()
        assert strategy is None
        assert raw is None
        assert record is not None
        assert -90 <= record["gps_lat"] <= 90
        assert 0 <= record["speed_mph"] <= 120


def test_memory_leak_anomaly_grows_buffer():
    before = memory_leak_bytes()
    rng = random.Random(0)
    # Force the memory_leak branch by calling the helper until it triggers.
    from ingestion.simulator import anomalies as anom

    anom._trigger_memory_leak(chunk_kb=64)
    assert memory_leak_bytes() > before

    # also exercise the probabilistic entry point without asserting which branch
    maybe_runtime_anomaly(
        rng=rng, failure_rate=1.0, memory_chunk_kb=32, cpu_spike_duration=0.01
    )
