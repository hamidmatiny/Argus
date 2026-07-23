"""CLI: ARGUS drift-monitor — Kafka validated → KS/Evidently → incidents.raw."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_REPO = _ROOT.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_GEN = _REPO / "shared" / "gen" / "python"
if _GEN.is_dir() and str(_GEN) not in sys.path:
    sys.path.insert(0, str(_GEN))

from kafka import KafkaConsumer  # noqa: E402

from analyzer import DriftAnalyzer, should_raise_incident  # noqa: E402
from config import (  # noqa: E402
    DRIFT_FEATURES,
    DRIFT_MIN_FEATURES_FOR_INCIDENT,
    GROUP_ID,
    HEALTH_PORT,
    INCIDENTS_TOPIC,
    KAFKA_BROKERS,
    METRICS_PORT,
    REPORTS_DIR,
    SOURCE_TOPIC,
)
from evidently_report import (  # noqa: E402
    run_evidently_drift_report,
    should_run_evidently,
)
from incidents import IncidentPublisher, build_incident_event  # noqa: E402
from metrics_server import DriftMetrics, start_http_server  # noqa: E402

# Reuse ingestion Avro decoder when available.
try:
    from ingestion.simulator.avro_codec import decode_confluent_avro, load_avro_schema
except ImportError:  # pragma: no cover
    decode_confluent_avro = None  # type: ignore[assignment]
    load_avro_schema = None  # type: ignore[assignment]


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "taskName",
            }:
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> logging.Logger:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logging.getLogger("argus.drift_monitor")


_shutdown = threading.Event()
_stats: dict[str, Any] = {
    "records_evaluated": 0,
    "windows_analyzed": 0,
    "incidents_published": 0,
    "baseline_ready": False,
    "baseline_source": None,
    "last_drifted_features": [],
}
# Readiness = live baseline frozen (not merely "Kafka consumer started").
_ready = False


def _handle_signal(signum: int, _frame: object) -> None:
    logging.getLogger("argus.drift_monitor").info(
        "shutdown_signal", extra={"signal": signum}
    )
    _shutdown.set()


def decode_value(value: bytes) -> dict | None:
    if decode_confluent_avro and load_avro_schema:
        try:
            _, record = decode_confluent_avro(value, schema=load_avro_schema())
            return dict(record)
        except Exception:
            pass
    try:
        obj = json.loads(value.decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def run() -> int:
    global _ready
    logger = setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    metrics = DriftMetrics()
    start_http_server(
        HEALTH_PORT,
        metrics=metrics,
        stats_provider=lambda: dict(_stats),
        ready_provider=lambda: _ready,
    )
    # Prometheus scrape often expects /metrics on the same or dedicated port.
    if METRICS_PORT != HEALTH_PORT:
        start_http_server(
            METRICS_PORT,
            metrics=metrics,
            stats_provider=lambda: dict(_stats),
            ready_provider=lambda: _ready,
        )

    analyzer = DriftAnalyzer()
    # Always accumulate a live baseline from telemetry.validated (ingest()).
    # Synthetic seed is an opt-in empty-topic fallback only; it never sets
    # baseline_ready and is replaced as soon as enough live samples arrive.
    # DRIFT_USE_LIVE_BASELINE defaults true; false enables synthetic cold-start.
    use_live = os.getenv("DRIFT_USE_LIVE_BASELINE", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    if not use_live:
        analyzer.seed_synthetic_baseline()
    _stats["baseline_ready"] = analyzer.baseline_ready
    _stats["baseline_source"] = analyzer.baseline_source

    publisher: IncidentPublisher | None = None
    consumer = None
    while (publisher is None or consumer is None) and not _shutdown.is_set():
        try:
            publisher = IncidentPublisher(
                brokers=KAFKA_BROKERS, topic=INCIDENTS_TOPIC
            )
            consumer = KafkaConsumer(
                SOURCE_TOPIC,
                bootstrap_servers=[
                    b.strip() for b in KAFKA_BROKERS.split(",") if b.strip()
                ],
                group_id=GROUP_ID,
                client_id="argus-drift-monitor",
                enable_auto_commit=True,
                # latest: build the live baseline from current traffic, not mixed
                # historical eras left in the topic across simulator restarts.
                auto_offset_reset=os.getenv("DRIFT_AUTO_OFFSET_RESET", "latest"),
                consumer_timeout_ms=1000,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kafka_connect_retry",
                extra={"error": str(exc), "brokers": KAFKA_BROKERS},
            )
            publisher = None
            consumer = None
            time.sleep(2.0)
    if publisher is None or consumer is None:
        logger.error("drift_monitor_aborted_no_kafka")
        return 1
    logger.info(
        "drift_monitor_started",
        extra={
            "source_topic": SOURCE_TOPIC,
            "incidents_topic": INCIDENTS_TOPIC,
            "features": list(DRIFT_FEATURES),
            "min_features_for_incident": DRIFT_MIN_FEATURES_FOR_INCIDENT,
            "health_port": HEALTH_PORT,
            "metrics_port": METRICS_PORT,
            "baseline_ready": analyzer.baseline_ready,
            "baseline_source": analyzer.baseline_source,
            "use_live_baseline": use_live,
        },
    )

    windows = 0
    last_progress = 0.0
    # Rising-edge only: don't republish while the breach condition persists.
    incident_active = False
    try:
        while not _shutdown.is_set():
            polled = False
            for message in consumer:
                polled = True
                record = decode_value(message.value)
                if not record:
                    continue
                report = analyzer.ingest(record)
                _stats["records_evaluated"] = analyzer.records_evaluated
                _stats["baseline_ready"] = analyzer.baseline_ready
                _stats["baseline_source"] = analyzer.baseline_source
                if analyzer.baseline_ready:
                    _ready = True
                metrics.records_evaluated.set(analyzer.records_evaluated)
                metrics.baseline_staleness.set(analyzer.baseline_staleness_seconds)

                if report is None:
                    continue

                windows += 1
                _stats["windows_analyzed"] = windows
                metrics.windows_analyzed.set(windows)
                scores = analyzer.feature_drift_scores(report)
                metrics.set_feature_scores(scores)
                _stats["last_drifted_features"] = report.get("drifted_features", [])

                if (
                    should_run_evidently(windows)
                    and analyzer._baseline_df is not None
                    and analyzer._last_window_df is not None
                ):
                    html_path, ev_scores = run_evidently_drift_report(
                        analyzer._baseline_df,
                        analyzer._last_window_df,
                        reports_dir=REPORTS_DIR,
                    )
                    if ev_scores:
                        metrics.set_feature_scores({**scores, **ev_scores})
                    if html_path:
                        logger.info(
                            "evidently_report_written",
                            extra={"path": str(html_path)},
                        )

                breached = should_raise_incident(
                    report, min_features=DRIFT_MIN_FEATURES_FOR_INCIDENT
                )
                if breached and not incident_active:
                    event = build_incident_event(
                        report, threshold=DRIFT_MIN_FEATURES_FOR_INCIDENT
                    )
                    publisher.publish(event)
                    _stats["incidents_published"] = publisher.published
                    metrics.incidents_published.set(publisher.published)
                    incident_active = True
                elif not breached:
                    incident_active = False

                now = time.monotonic()
                if now - last_progress >= 10.0:
                    logger.info("drift_progress", extra=dict(_stats))
                    last_progress = now

            if not polled:
                time.sleep(0.05)
    finally:
        publisher.close()
        consumer.close()
        logger.info("drift_monitor_stopped", extra=dict(_stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
