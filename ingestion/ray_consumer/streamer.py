"""Ray DataStreamer actor pool — partition-parallel Kafka consume/normalize/publish."""

from __future__ import annotations

import logging
import time
from typing import Any

import ray
from kafka import KafkaConsumer, KafkaProducer

from ingestion.ray_consumer.normalize import decode_kafka_value, normalize_record
from ingestion.simulator.avro_codec import encode_confluent_avro, load_avro_schema
from ingestion.simulator.kafka_publisher import ensure_schema_registered

logger = logging.getLogger("argus.ingestion.ray_consumer")


@ray.remote
class DataStreamer:
    """
    Stateful Ray actor owning one vehicle/camera partition slice.

    Mirrors sentinel-ray's DataStreamer pattern: actors process partitions
    concurrently via ray.get on a pool of futures.
    """

    def __init__(
        self,
        *,
        partition_id: str,
        brokers: str,
        source_topic: str,
        dest_topic: str,
        group_id: str,
        schema_registry_url: str,
        schema_id: int,
    ) -> None:
        self.partition_id = partition_id
        self.source_topic = source_topic
        self.dest_topic = dest_topic
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

    def process_batch(self, max_messages: int = 50) -> dict[str, Any]:
        """Pull up to max_messages, normalize, republish clean events."""
        processed = 0
        for message in self._consumer:
            self._stats["consumed"] += 1
            try:
                record, codec = decode_kafka_value(message.value)
                if record is None:
                    self._stats["quarantined"] += 1
                    logger.warning(
                        "quarantine_raw",
                        extra={"partition_id": self.partition_id, "codec": codec},
                    )
                else:
                    normalized, issues = normalize_record(record)
                    if normalized is None:
                        self._stats["quarantined"] += 1
                        logger.warning(
                            "quarantine_invalid",
                            extra={
                                "partition_id": self.partition_id,
                                "issues": issues,
                            },
                        )
                    else:
                        if issues:
                            logger.info(
                                "normalized_with_issues",
                                extra={
                                    "partition_id": self.partition_id,
                                    "issues": issues,
                                    "vehicle_id": normalized.get("vehicle_id"),
                                },
                            )
                        payload = encode_confluent_avro(
                            normalized,
                            schema=self.schema,
                            schema_id=self.schema_id,
                        )
                        key = str(normalized["vehicle_id"]).encode("utf-8")
                        self._producer.send(self.dest_topic, key=key, value=payload)
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


def initialize_ray(*, num_cpus: int, dashboard_host: str, dashboard_port: int) -> None:
    ray.init(
        ignore_reinit_error=True,
        num_cpus=num_cpus,
        include_dashboard=True,
        dashboard_host=dashboard_host,
        dashboard_port=dashboard_port,
        logging_level=logging.WARNING,
    )
    # Brief pause so dashboard binds before health reports ready.
    time.sleep(0.5)
