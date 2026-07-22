"""Publish IncidentEvent messages to Kafka (shared proto / Pydantic shape)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from kafka import KafkaProducer

logger = logging.getLogger("argus.drift_monitor.incidents")


def build_incident_event(
    report: dict[str, Any],
    *,
    threshold: int,
) -> dict[str, Any]:
    """
    Build an IncidentEvent dict matching shared/proto argus.v1.IncidentEvent.

    observed_value = drifted feature count; threshold = DRIFT_MIN_FEATURES_FOR_INCIDENT.
    """
    drifted = list(report.get("drifted_features") or [])
    return {
        "incident_id": f"drift-{uuid.uuid4().hex[:12]}",
        "severity": "INCIDENT_SEVERITY_CRITICAL",
        "source_service": "drift-monitor",
        "metric_name": "drifted_feature_count",
        "threshold": float(threshold),
        "observed_value": float(len(drifted)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "INCIDENT_STATUS_OPEN",
        # Extensions for operators / incident-engine (ignored by strict proto consumers).
        "drifted_features": drifted,
        "window_size": report.get("window_size"),
        "alpha": report.get("alpha"),
    }


def encode_incident_protobuf(event: dict[str, Any]) -> bytes | None:
    """Serialize with generated protobuf if available; else None."""
    try:
        from argus.v1 import incident_pb2
    except ImportError:
        try:
            import sys
            from pathlib import Path

            gen = Path(__file__).resolve().parents[1] / "shared" / "gen" / "python"
            if str(gen) not in sys.path:
                sys.path.insert(0, str(gen))
            from argus.v1 import incident_pb2
        except ImportError:
            return None

    severity = getattr(
        incident_pb2,
        event.get("severity", "INCIDENT_SEVERITY_CRITICAL"),
        incident_pb2.INCIDENT_SEVERITY_CRITICAL,
    )
    status = getattr(
        incident_pb2,
        event.get("status", "INCIDENT_STATUS_OPEN"),
        incident_pb2.INCIDENT_STATUS_OPEN,
    )
    msg = incident_pb2.IncidentEvent(
        incident_id=str(event["incident_id"]),
        severity=severity,
        source_service=str(event["source_service"]),
        metric_name=str(event["metric_name"]),
        threshold=float(event["threshold"]),
        observed_value=float(event["observed_value"]),
        timestamp=str(event["timestamp"]),
        status=status,
    )
    return msg.SerializeToString()


class IncidentPublisher:
    """Publishes IncidentEvent JSON (+ optional protobuf key headers) to Kafka."""

    def __init__(self, *, brokers: str, topic: str) -> None:
        self.topic = topic
        self._producer = KafkaProducer(
            bootstrap_servers=[b.strip() for b in brokers.split(",") if b.strip()],
            acks="all",
            linger_ms=10,
            client_id="argus-drift-monitor",
        )
        self.published = 0

    def publish(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, default=str).encode("utf-8")
        headers = [("content-type", b"application/json")]
        pb = encode_incident_protobuf(event)
        if pb is not None:
            headers.append(("protobuf-schema", b"argus.v1.IncidentEvent"))
            # Keep JSON as the value for polyglot consumers; attach pb as header blob size note.
            headers.append(("protobuf-bytes", str(len(pb)).encode("ascii")))
        self._producer.send(
            self.topic,
            key=str(event["incident_id"]).encode("utf-8"),
            value=payload,
            headers=headers,
        )
        self._producer.flush()
        self.published += 1
        logger.warning(
            "incident_published",
            extra={
                "incident_id": event["incident_id"],
                "observed_value": event["observed_value"],
                "threshold": event["threshold"],
                "drifted_features": event.get("drifted_features"),
                "topic": self.topic,
            },
        )

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()
