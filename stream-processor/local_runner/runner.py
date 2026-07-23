"""Pure-Python Kafka QA gate (non-Flink fallback)."""

from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Any

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

from serdes.kafka_codec import (
    decode_value,
    encode_json,
    encode_telemetry,
    ensure_schema_registered,
    load_avro_schema,
)
from validation.metrics import (
    QA_QUARANTINE_RATE_THRESHOLD,
    QA_WINDOW_EVENTS,
    TumblingQuarantineWindow,
)
from validation.rules import build_quarantine_record, validate_telemetry_event

logger = logging.getLogger("argus.stream_processor.local")

_shutdown = threading.Event()


def _handle_signal(signum: int, _frame: object) -> None:
    logger.info("shutdown_signal", extra={"signal": signum})
    _shutdown.set()


def run_local(
    *,
    brokers: str,
    source_topic: str,
    validated_topic: str,
    quarantine_topic: str,
    metrics_topic: str,
    group_id: str,
    schema_registry_url: str,
    window_size: int = QA_WINDOW_EVENTS,
    threshold: float = QA_QUARANTINE_RATE_THRESHOLD,
    max_messages: int | None = None,
    idle_stop_seconds: float | None = None,
    stats: dict[str, int] | None = None,
) -> dict[str, int]:
    """
    Consume normalized telemetry, validate, route, and emit window metrics.

    ``max_messages`` / ``idle_stop_seconds`` support tests; production leaves both None.
    Pass a mutable ``stats`` dict to expose live counters to /health.
    """
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    _shutdown.clear()

    schema = load_avro_schema()
    schema_id = 0
    try:
        schema_id = ensure_schema_registered(
            schema_registry_url,
            "argus.telemetry.TelemetryEvent-value",
            schema,
        )
    except Exception as exc:  # noqa: BLE001 — registry optional at boot; JSON path still works
        logger.warning(
            "schema_registry_unavailable",
            extra={"error": str(exc), "url": schema_registry_url},
        )
    bootstrap = [b.strip() for b in brokers.split(",") if b.strip()]
    consumer = None
    while consumer is None and not _shutdown.is_set():
        try:
            consumer = KafkaConsumer(
                source_topic,
                bootstrap_servers=bootstrap,
                group_id=group_id,
                client_id="argus-stream-processor-local",
                enable_auto_commit=True,
                auto_offset_reset="earliest",
                max_partition_fetch_bytes=2 * 1024 * 1024,
                fetch_max_bytes=10 * 1024 * 1024,
                consumer_timeout_ms=500,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kafka_connect_retry",
                extra={"error": str(exc), "brokers": brokers},
            )
            time.sleep(2)
    if consumer is None:
        return stats if stats is not None else {}
    producer = KafkaProducer(
        bootstrap_servers=bootstrap,
        client_id="argus-stream-processor-producer",
        acks="all",
        linger_ms=10,
    )
    windows = TumblingQuarantineWindow(window_size=window_size, threshold=threshold)
    if stats is None:
        stats = {}
    stats.update(
        {
            "consumed": 0,
            "validated": 0,
            "quarantined": 0,
            "metrics_emitted": 0,
            "decode_failures": 0,
        }
    )
    last_msg_at = time.monotonic()
    last_progress_log = 0.0
    logger.info(
        "local_runner_started",
        extra={
            "source_topic": source_topic,
            "validated_topic": validated_topic,
            "quarantine_topic": quarantine_topic,
            "metrics_topic": metrics_topic,
            "window_size": window_size,
        },
    )

    try:
        while not _shutdown.is_set():
            try:
                batches = consumer.poll(timeout_ms=1000, max_records=100)
            except KafkaError as exc:
                logger.warning("kafka_poll_error", extra={"error": str(exc)})
                time.sleep(1.0)
                continue

            if not batches:
                if (
                    idle_stop_seconds is not None
                    and (time.monotonic() - last_msg_at) >= idle_stop_seconds
                ):
                    break
                continue

            for _tp, messages in batches.items():
                for message in messages:
                    last_msg_at = time.monotonic()
                    stats["consumed"] += 1
                    try:
                        from metrics_prom import RECORDS, WINDOWS
                        from otel_setup import start_span
                    except ImportError:  # pragma: no cover
                        RECORDS = WINDOWS = None  # type: ignore[assignment]
                        start_span = None  # type: ignore[assignment]

                    span_cm = (
                        start_span("qa.validate_record", messaging_system="kafka")
                        if start_span
                        else None
                    )
                    if span_cm is None:
                        from contextlib import nullcontext

                        span_cm = nullcontext()

                    with span_cm:
                        record, codec = decode_value(message.value)
                        if record is None:
                            stats["decode_failures"] += 1
                            stats["quarantined"] += 1
                            if RECORDS is not None:
                                RECORDS.labels(result="quarantined").inc()
                            q = build_quarantine_record(
                                {"_raw_codec": codec},
                                validate_telemetry_event(None),
                                source_topic=source_topic,
                            )
                            q["reason"] = f"decode_failed:{codec}"
                            q["field"] = "_payload"
                            q["rule"] = "decode"
                            producer.send(
                                quarantine_topic,
                                key=b"unknown",
                                value=encode_json(q),
                            )
                            continue

                        result = validate_telemetry_event(record)
                        vehicle_id = str(record.get("vehicle_id") or "unknown")
                        if result.ok:
                            stats["validated"] += 1
                            if RECORDS is not None:
                                RECORDS.labels(result="validated").inc()
                            producer.send(
                                validated_topic,
                                key=vehicle_id.encode("utf-8"),
                                value=encode_telemetry(record, schema_id=schema_id),
                            )
                            metric = windows.observe(vehicle_id, quarantined=False)
                        else:
                            stats["quarantined"] += 1
                            if RECORDS is not None:
                                RECORDS.labels(result="quarantined").inc()
                            qrec = build_quarantine_record(
                                record, result, source_topic=source_topic
                            )
                            producer.send(
                                quarantine_topic,
                                key=vehicle_id.encode("utf-8"),
                                value=encode_json(qrec),
                            )
                            metric = windows.observe(vehicle_id, quarantined=True)

                        if metric is not None:
                            stats["metrics_emitted"] += 1
                            if WINDOWS is not None:
                                WINDOWS.inc()
                            producer.send(
                                metrics_topic,
                                key=vehicle_id.encode("utf-8"),
                                value=encode_json(metric.to_dict()),
                            )
                            if metric.exceeded:
                                logger.warning(
                                    "qa_quarantine_rate_exceeded",
                                    extra=metric.to_dict(),
                                )

                    if max_messages is not None and stats["consumed"] >= max_messages:
                        _shutdown.set()
                        break
                if _shutdown.is_set():
                    break

            producer.flush()
            now = time.monotonic()
            if now - last_progress_log >= 10.0:
                logger.info("qa_progress", extra=dict(stats))
                last_progress_log = now

            if max_messages is not None and stats["consumed"] >= max_messages:
                break
    finally:
        producer.flush()
        producer.close()
        consumer.close()
        logger.info("local_runner_stopped", extra=dict(stats))
    return stats


def process_record(
    record: dict[str, Any] | None,
    *,
    windows: TumblingQuarantineWindow,
    source_topic: str = "telemetry.normalized",
) -> dict[str, Any]:
    """
    Pure routing helper for tests — no Kafka I/O.

    Returns dict with keys: route (validated|quarantine), payload, metric|None
    """
    result = validate_telemetry_event(record)
    if not result.ok or record is None:
        vehicle_id = str((record or {}).get("vehicle_id") or "unknown")
        metric = windows.observe(vehicle_id, quarantined=True)
        return {
            "route": "quarantine",
            "payload": build_quarantine_record(
                record, result, source_topic=source_topic
            ),
            "metric": metric.to_dict() if metric else None,
        }
    vehicle_id = str(record.get("vehicle_id") or "unknown")
    metric = windows.observe(vehicle_id, quarantined=False)
    return {
        "route": "validated",
        "payload": record,
        "metric": metric.to_dict() if metric else None,
    }
