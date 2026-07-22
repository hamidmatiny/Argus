"""PyFlink streaming QA job — same validation + routing as the local runner."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Iterable

from validation.metrics import (
    QA_QUARANTINE_RATE_THRESHOLD,
    QA_WINDOW_EVENTS,
    TumblingQuarantineWindow,
)
from validation.rules import build_quarantine_record, validate_telemetry_event

logger = logging.getLogger("argus.stream_processor.flink")


def map_validation(raw_json: str) -> tuple[str, str]:
    """
    Flink-friendly map: input JSON string → (route, output_json).

    route is ``validated`` | ``quarantine``.
    """
    try:
        record = json.loads(raw_json)
    except json.JSONDecodeError:
        record = None
    result = validate_telemetry_event(record if isinstance(record, dict) else None)
    if result.ok and isinstance(record, dict):
        return "validated", json.dumps(record, default=str)
    q = build_quarantine_record(
        record if isinstance(record, dict) else None,
        result,
    )
    return "quarantine", json.dumps(q, default=str)


class QuarantineRateAggregator:
    """Serializable helper used by Flink keyed process / local reduce tests."""

    def __init__(
        self,
        window_size: int = QA_WINDOW_EVENTS,
        threshold: float = QA_QUARANTINE_RATE_THRESHOLD,
    ) -> None:
        self._windows = TumblingQuarantineWindow(window_size, threshold)

    def add(self, vehicle_id: str, quarantined: bool) -> dict[str, Any] | None:
        metric = self._windows.observe(vehicle_id, quarantined)
        return metric.to_dict() if metric else None


def build_flink_job(
    *,
    brokers: str,
    source_topic: str,
    validated_topic: str,
    quarantine_topic: str,
    metrics_topic: str,
    group_id: str,
    window_size: int = QA_WINDOW_EVENTS,
    parallelism: int = 1,
) -> Any:
    """
    Construct and return a configured ``StreamExecutionEnvironment``.

    Requires ``apache-flink`` (PyFlink) and Kafka connector jars on the classpath.
    Uses JSON strings on the wire for the Flink path (Avro remains on the local
    runner / ingestion path); both engines share ``validate_telemetry_event``.
    """
    try:
        from pyflink.common import Types, WatermarkStrategy
        from pyflink.common.serialization import SimpleStringSchema
        from pyflink.datastream import StreamExecutionEnvironment
        from pyflink.datastream.connectors.kafka import (
            KafkaOffsetsInitializer,
            KafkaRecordSerializationSchema,
            KafkaSink,
            KafkaSource,
        )
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PyFlink is not installed. Use --engine=local or pip install apache-flink"
        ) from exc

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(parallelism)
    # Enable checkpointing for exactly-once sink semantics when the cluster supports it.
    env.enable_checkpointing(10_000)

    jar_path = os.getenv(
        "FLINK_KAFKA_CONNECTOR_JAR",
        "/opt/flink/lib/flink-sql-connector-kafka.jar",
    )
    if os.path.isfile(jar_path):
        env.add_jars(f"file://{jar_path}")

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(brokers)
        .set_topics(source_topic)
        .set_group_id(group_id)
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    stream = env.from_source(
        source, WatermarkStrategy.no_watermarks(), "telemetry.normalized"
    )

    def _route(value: str) -> tuple[str, str]:
        return map_validation(value)

    routed = stream.map(
        _route, output_type=Types.TUPLE([Types.STRING(), Types.STRING()])
    )

    validated = routed.filter(lambda t: t[0] == "validated").map(
        lambda t: t[1], output_type=Types.STRING()
    )
    quarantined = routed.filter(lambda t: t[0] == "quarantine").map(
        lambda t: t[1], output_type=Types.STRING()
    )

    def _sink(topic: str) -> KafkaSink:
        return (
            KafkaSink.builder()
            .set_bootstrap_servers(brokers)
            .set_record_serializer(
                KafkaRecordSerializationSchema.builder()
                .set_topic(topic)
                .set_value_serialization_schema(SimpleStringSchema())
                .build()
            )
            .build()
        )

    validated.sink_to(_sink(validated_topic))
    quarantined.sink_to(_sink(quarantine_topic))

    # Metrics: keyed tumbling count window approximated via flat-map + keyed state
    # in a ProcessFunction. For portability across PyFlink versions we emit metrics
    # from a stateful map that closes windows every ``window_size`` events.
    aggregator = QuarantineRateAggregator(window_size=window_size)

    def _metric_flat(value: str) -> Iterable[str]:
        route, payload = map_validation(value)
        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            return []
        vehicle_id = str(body.get("vehicle_id") or "unknown")
        metric = aggregator.add(vehicle_id, quarantined=(route == "quarantine"))
        if metric is None:
            return []
        metric["emitted_at"] = datetime.now(timezone.utc).isoformat()
        return [json.dumps(metric)]

    metrics = stream.flat_map(_metric_flat, output_type=Types.STRING())
    metrics.sink_to(_sink(metrics_topic))

    logger.info(
        "flink_job_built",
        extra={
            "source_topic": source_topic,
            "validated_topic": validated_topic,
            "quarantine_topic": quarantine_topic,
            "metrics_topic": metrics_topic,
            "window_size": window_size,
        },
    )
    return env


def run_flink(**kwargs: Any) -> None:
    env = build_flink_job(**kwargs)
    env.execute("argus-stream-processor-qa")
