"""Unit tests for incident publishing (no live Kafka required)."""

from __future__ import annotations

from typing import Any

import pytest

from incidents import IncidentPublisher, build_incident_event, encode_incident_protobuf


def _sample_report(**overrides: Any) -> dict[str, Any]:
    base = {
        "drifted_features": ["speed_mph", "brake_pressure"],
        "window_size": 40,
        "alpha": 0.05,
    }
    base.update(overrides)
    return base


def test_build_incident_event_shape():
    event = build_incident_event(_sample_report(), threshold=2)
    assert event["source_service"] == "drift-monitor"
    assert event["metric_name"] == "drifted_feature_count"
    assert event["severity"] == "INCIDENT_SEVERITY_CRITICAL"
    assert event["status"] == "INCIDENT_STATUS_OPEN"
    assert event["threshold"] == 2.0
    assert event["observed_value"] == 2.0
    assert event["drifted_features"] == ["speed_mph", "brake_pressure"]
    assert event["incident_id"].startswith("drift-")


def test_encode_incident_protobuf_roundtrip_or_none():
    event = build_incident_event(_sample_report(), threshold=2)
    encoded = encode_incident_protobuf(event)
    # CI installs protobuf via contracts/gen path; if unavailable, returns None.
    if encoded is None:
        pytest.skip("generated incident_pb2 / protobuf not importable in this env")
    assert isinstance(encoded, (bytes, bytearray))
    assert len(encoded) > 0


def test_incident_publisher_sends_json_with_mocked_producer(monkeypatch):
    sent: list[dict[str, Any]] = []

    class _FakeProducer:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def send(self, topic, key=None, value=None, headers=None):  # noqa: ANN001
            sent.append(
                {
                    "topic": topic,
                    "key": key,
                    "value": value,
                    "headers": headers,
                }
            )

        def flush(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr("incidents.KafkaProducer", _FakeProducer)
    # Force protobuf path off so this test stays independent of gen/protobuf.
    monkeypatch.setattr("incidents.encode_incident_protobuf", lambda _event: None)

    pub = IncidentPublisher(brokers="localhost:9092", topic="incidents.raw")
    event = build_incident_event(_sample_report(), threshold=2)
    pub.publish(event)
    pub.close()

    assert pub.published == 1
    assert len(sent) == 1
    assert sent[0]["topic"] == "incidents.raw"
    assert sent[0]["key"] == event["incident_id"].encode("utf-8")
    assert b"drift-monitor" in sent[0]["value"]
    header_names = [h[0] for h in sent[0]["headers"]]
    assert "content-type" in header_names
    assert "protobuf-schema" not in header_names


def test_incident_publisher_attaches_protobuf_headers_when_encoded(monkeypatch):
    sent: list[dict[str, Any]] = []

    class _FakeProducer:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def send(self, topic, key=None, value=None, headers=None):  # noqa: ANN001
            sent.append({"headers": headers})

        def flush(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr("incidents.KafkaProducer", _FakeProducer)
    monkeypatch.setattr("incidents.encode_incident_protobuf", lambda _event: b"\x00\x01\x02")

    pub = IncidentPublisher(brokers="broker:9092", topic="incidents.raw")
    pub.publish(build_incident_event(_sample_report(), threshold=2))
    pub.close()

    headers = {k: v for k, v in sent[0]["headers"]}
    assert headers["protobuf-schema"] == b"argus.v1.IncidentEvent"
    assert headers["protobuf-bytes"] == b"3"
