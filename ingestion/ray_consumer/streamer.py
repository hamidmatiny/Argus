"""Ray DataStreamer actor pool — partition-parallel Kafka consume/normalize/publish."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import ray
from kafka import KafkaConsumer, KafkaProducer

from ingestion.ray_consumer.normalize import (
    build_structural_quarantine,
    decode_kafka_value,
    normalize_record,
)
from ingestion.simulator.avro_codec import encode_confluent_avro, load_avro_schema
from ingestion.simulator.kafka_publisher import ensure_schema_registered

logger = logging.getLogger("argus.ingestion.ray_consumer")


@ray.remote
class DataStreamer:
    """
    Stateful Ray actor owning one vehicle/camera partition slice.

    Pass-through normalizer: decode/coerce only. Semantic QA belongs to
    stream-processor. Structural failures go to ``telemetry.quarantine``.
    """

    def __init__(
        self,
        *,
        partition_id: str,
        brokers: str,
        source_topic: str,
        dest_topic: str,
        quarantine_topic: str,
        group_id: str,
        schema_registry_url: str,
        schema_id: int,
    ) -> None:
        self.partition_id = partition_id
        self.source_topic = source_topic
        self.dest_topic = dest_topic
        self.quarantine_topic = quarantine_topic
        self.schema = load_avro_schema()
        self.schema_id = schema_id
        self._stats = {
            "consumed": 0,
            "published": 0,
            "quarantined": 0,
            "errors": 0,
        }
        self._consumer = KafkaConsumer(
            source_topic,
            bootstrap_servers=[b.strip() for b in brokers.split(",") if b.strip()],
            group_id=group_id,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            consumer_timeout_ms=500,
        )
        self._producer = KafkaProducer(
            bootstrap_servers=[b.strip() for b in brokers.split(",") if b.strip()],
            acks="all",
            linger_ms=20,
        )

    def _publish_quarantine(
        self, record: dict[str, Any] | None, issues: list[str]
    ) -> None:
        q = build_structural_quarantine(
            record, issues, source_topic=self.source_topic
        )
        key = str(q.get("vehicle_id") or "unknown").encode("utf-8")
        self._producer.send(
            self.quarantine_topic,
            key=key,
            value=json.dumps(q, default=str).encode("utf-8"),
        )
        self._stats["quarantined"] += 1
        logger.warning(
            "structural_quarantine",
            extra={
                "partition_id": self.partition_id,
                "issues": issues,
                "field": q.get("field"),
                "source_topic": self.source_topic,
            },
        )

    def process_batch(self, max_messages: int = 50) -> dict[str, Any]:
        """Pull up to max_messages, pass-through normalize, republish or quarantine."""
        processed = 0
        for message in self._consumer:
            self._stats["consumed"] += 1
            try:
                record, codec = decode_kafka_value(message.value)
                if record is None:
                    self._publish_quarantine(
                        {"_raw_codec": codec},
                        ["decode_failed"],
                    )
                else:
                    normalized, issues = normalize_record(record)
                    if normalized is None:
                        self._publish_quarantine(record, issues)
                    else:
                        try:
                            payload = encode_confluent_avro(
                                normalized,
                                schema=self.schema,
                                schema_id=self.schema_id,
                            )
                        except Exception:
                            self._publish_quarantine(
                                normalized, ["avro_encode_failed"]
                            )
                        else:
                            key = str(normalized["vehicle_id"]).encode("utf-8")
                            self._producer.send(
                                self.dest_topic, key=key, value=payload
                            )
                            self._stats["published"] += 1
            except Exception as exc:  # noqa: BLE001 — keep actor alive
                self._stats["errors"] += 1
                logger.exception(
                    "process_error",
                    extra={"partition_id": self.partition_id, "error": str(exc)},
                )
            processed += 1
            if processed >= max_messages:
                break
        self._producer.flush()
        return {"partition_id": self.partition_id, **dict(self._stats)}

    def stats(self) -> dict[str, Any]:
        return {"partition_id": self.partition_id, **dict(self._stats)}

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()
        self._consumer.close()


def create_streamer_pool(
    *,
    partition_ids: list[str],
    brokers: str,
    source_topic: str,
    dest_topic: str,
    quarantine_topic: str,
    group_id: str,
    schema_registry_url: str,
) -> list[Any]:
    schema = load_avro_schema()
    schema_id = ensure_schema_registered(
        schema_registry_url,
        "argus.telemetry.TelemetryEvent-value",
        schema,
    )
    return [
        DataStreamer.remote(
            partition_id=pid,
            brokers=brokers,
            source_topic=source_topic,
            dest_topic=dest_topic,
            quarantine_topic=quarantine_topic,
            group_id=group_id,
            schema_registry_url=schema_registry_url,
            schema_id=schema_id,
        )
        for pid in partition_ids
    ]


def process_partitions_concurrently(
    streamers: list[Any],
    *,
    max_messages: int = 50,
) -> list[dict[str, Any]]:
    """Fan-out process_batch across the actor pool (sentinel-ray style)."""
    futures = [s.process_batch.remote(max_messages) for s in streamers]
    return list(ray.get(futures))


def initialize_ray(
    *,
    num_cpus: int,
    dashboard_host: str,
    dashboard_port: int,
    object_store_memory: int,
    memory: int,
    include_dashboard: bool = False,
) -> None:
    """
    Start a local Ray node with explicit memory budgets.

    Inside cgroup-limited Docker containers Ray's auto memory detection often
    resolves available memory to 0 and refuses to start. Pass explicit
    ``object_store_memory`` and ``_memory`` instead of relying on fractions.

    The Ray dashboard is disabled by default under Docker: its multi-process
    UI stack alone can exceed a 2Gi cgroup before any actors start.
    """
    logger.info(
        "ray_init",
        extra={
            "num_cpus": num_cpus,
            "object_store_memory": object_store_memory,
            "memory": memory,
            "include_dashboard": include_dashboard,
            "dashboard_port": dashboard_port,
        },
    )
    init_kwargs: dict[str, Any] = {
        "ignore_reinit_error": True,
        "num_cpus": num_cpus,
        "include_dashboard": include_dashboard,
        "object_store_memory": object_store_memory,
        "_memory": memory,
        "logging_level": logging.WARNING,
    }
    if include_dashboard:
        init_kwargs["dashboard_host"] = dashboard_host
        init_kwargs["dashboard_port"] = dashboard_port
    ray.init(**init_kwargs)
    # Brief pause so dashboard (if enabled) binds before health reports ready.
    time.sleep(0.5)
