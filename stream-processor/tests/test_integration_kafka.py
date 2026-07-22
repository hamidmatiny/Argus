"""Kafka integration: known-good / known-bad land on correct topics (local engine)."""

from __future__ import annotations

import json
import os
import socket
import time
import uuid

import pytest
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable

from serdes.kafka_codec import encode_json, encode_telemetry, ensure_schema_registered, load_avro_schema
from local_runner.runner import run_local

BROKER = os.getenv("KAFKA_BROKERS", "localhost:19092")
SCHEMA_REGISTRY = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:18081")


def _broker_up(hostport: str) -> bool:
    host, _, port_s = hostport.partition(":")
    port = int(port_s or "9092")
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _broker_up(BROKER.split(",")[0]),
    reason=f"Kafka broker not reachable at {BROKER}",
)


def _good(vehicle_id: str = "VH-0000099") -> dict:
    return {
        "vehicle_id": vehicle_id,
        "trip_id": "integration-trip",
        "timestamp": "2026-07-22T18:30:00Z",
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


def test_local_engine_routes_good_and_bad_to_correct_topics():
    suffix = uuid.uuid4().hex[:8]
    source = f"test.qa.source.{suffix}"
    validated = f"test.qa.validated.{suffix}"
    quarantine = f"test.qa.quarantine.{suffix}"
    metrics = f"test.qa.metrics.{suffix}"
    group = f"test-qa-{suffix}"

    schema = load_avro_schema()
    try:
        schema_id = ensure_schema_registered(
            SCHEMA_REGISTRY, "argus.telemetry.TelemetryEvent-value", schema
        )
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"schema registry unavailable: {exc}")

    producer = KafkaProducer(bootstrap_servers=BROKER.split(","), acks="all")
    good = _good("VH-0000099")
    bad = _good("VH-0000098")
    bad["gps_lat"] = 999.0

    producer.send(source, key=b"VH-0000099", value=encode_telemetry(good, schema_id=schema_id))
    producer.send(source, key=b"VH-0000098", value=encode_telemetry(bad, schema_id=schema_id))
    # Also send JSON bad for decode variety
    producer.send(
        source,
        key=b"VH-0000097",
        value=encode_json({**_good("VH-0000097"), "speed_mph": -5.0}),
    )
    producer.flush()
    producer.close()

    stats = run_local(
        brokers=BROKER,
        source_topic=source,
        validated_topic=validated,
        quarantine_topic=quarantine,
        metrics_topic=metrics,
        group_id=group,
        schema_registry_url=SCHEMA_REGISTRY,
        window_size=100,
        max_messages=3,
        idle_stop_seconds=5.0,
    )
    assert stats["consumed"] == 3
    assert stats["validated"] >= 1
    assert stats["quarantined"] >= 1

    def _drain(topic: str, expect: int, timeout: float = 10.0) -> list[bytes]:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=BROKER.split(","),
            auto_offset_reset="earliest",
            consumer_timeout_ms=1000,
            group_id=f"drain-{topic}-{suffix}",
        )
        deadline = time.monotonic() + timeout
        found: list[bytes] = []
        while time.monotonic() < deadline and len(found) < expect:
            for msg in consumer:
                found.append(msg.value)
                if len(found) >= expect:
                    break
        consumer.close()
        return found

    validated_msgs = _drain(validated, 1)
    quarantine_msgs = _drain(quarantine, 2)
    assert len(validated_msgs) >= 1
    assert len(quarantine_msgs) >= 2

    # Quarantine payloads are JSON with structured rejection reasons.
    q0 = json.loads(quarantine_msgs[0].decode())
    assert "field" in q0 and "rule" in q0 and "raw_payload" in q0
