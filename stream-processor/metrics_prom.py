"""Prometheus exposition for the stream-processor QA gate."""

from __future__ import annotations

from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, generate_latest

REGISTRY = CollectorRegistry()

RECORDS = Counter(
    "argus_qa_records_total",
    "Telemetry records processed by the QA gate",
    ["result"],
    registry=REGISTRY,
)
WINDOWS = Counter(
    "argus_qa_windows_emitted_total",
    "Per-vehicle QA metric windows published to Kafka",
    registry=REGISTRY,
)
PASS_RATIO = Gauge(
    "argus_qa_pass_ratio",
    "Validated / (validated + quarantined) over process lifetime",
    registry=REGISTRY,
)
READY = Gauge(
    "argus_qa_ready",
    "1 when the QA gate is ready to serve traffic",
    registry=REGISTRY,
)


def observe_stats(stats: dict[str, Any], *, ready: bool) -> None:
    """Refresh gauges from the live stats dict (counters are incremented in-runner)."""
    validated = float(stats.get("validated", 0))
    quarantined = float(stats.get("quarantined", 0))
    denom = validated + quarantined
    PASS_RATIO.set(validated / denom if denom else 1.0)
    READY.set(1.0 if ready else 0.0)


def render() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
