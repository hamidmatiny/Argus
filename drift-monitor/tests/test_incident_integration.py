"""Integration: synthetic drift publishes an IncidentEvent to Kafka (or in-memory)."""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from typing import Any

import pytest
from kafka import KafkaConsumer

from analyzer import DriftAnalyzer, generate_baseline_data, should_raise_incident
from config import DRIFT_FEATURES
from incidents import IncidentPublisher, build_incident_event


class _InMemoryPublisher:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.published = 0

    def publish(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        self.published += 1

    def close(self) -> None:
        return


def _broker_up(hostport: str) -> bool:
    host, _, port_s = hostport.partition(":")
    try:
        with socket.create_connection((host, int(port_s or "9092")), timeout=1.5):
            return True
    except OSError:
        return False


def _live_baseline(analyzer: DriftAnalyzer, n: int | None = None) -> None:
    count = n or analyzer.baseline_samples
    for _ in range(count):
        row = {
            f: float(generate_baseline_data(1, seed=None).iloc[0][f])
            for f in DRIFT_FEATURES
        }
        analyzer.ingest(row)
    assert analyzer.baseline_ready


def test_synthetic_drift_triggers_incident_in_memory():
    analyzer = DriftAnalyzer(
        baseline_samples=100,
        warmup_samples=0,
        window_size=40,
        min_features_for_incident=2,
    )
    _live_baseline(analyzer)
    publisher = _InMemoryPublisher()

    report = None
    for i in range(40):
        row = {f: 0.0 for f in DRIFT_FEATURES}
        row["speed_mph"] = 90.0 + i * 0.01
        row["brake_pressure"] = 2.5
        row["lidar_temp_c"] = 80.0
        row["compute_load_pct"] = 95.0
        report = analyzer.ingest(row)

    assert report is not None
    assert should_raise_incident(report, min_features=2)
    event = build_incident_event(report, threshold=2)
    publisher.publish(event)
    assert publisher.published == 1
    assert publisher.events[0]["source_service"] == "drift-monitor"
    assert publisher.events[0]["observed_value"] >= 2.0


@pytest.mark.skipif(
    not _broker_up(os.getenv("KAFKA_BROKERS", "localhost:19092").split(",")[0]),
    reason="Kafka broker not reachable",
)
def test_incident_published_to_kafka_topic():
    brokers = os.getenv("KAFKA_BROKERS", "localhost:19092")
    topic = f"test.incidents.raw.{uuid.uuid4().hex[:8]}"
    analyzer = DriftAnalyzer(
        baseline_samples=80,
        warmup_samples=0,
        window_size=30,
        min_features_for_incident=2,
    )
    _live_baseline(analyzer)
    publisher = IncidentPublisher(brokers=brokers, topic=topic)

    report = None
    for _ in range(30):
        row = {
            "speed_mph": 100.0,
            "brake_pressure": 3.0,
            "lidar_temp_c": 90.0,
            "compute_load_pct": 99.0,
        }
        report = analyzer.ingest(row)
    assert report is not None and should_raise_incident(report, min_features=2)
    event = build_incident_event(report, threshold=2)
    publisher.publish(event)
    publisher.close()

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=brokers.split(","),
        auto_offset_reset="earliest",
        consumer_timeout_ms=5000,
        group_id=f"drift-it-{uuid.uuid4().hex[:8]}",
    )
    found = None
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and found is None:
        for msg in consumer:
            found = json.loads(msg.value.decode())
            break
    consumer.close()
    assert found is not None
    assert found["source_service"] == "drift-monitor"
    assert found["metric_name"] == "drifted_feature_count"
    assert found["severity"] == "INCIDENT_SEVERITY_CRITICAL"
