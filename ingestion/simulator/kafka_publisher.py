"""Kafka producer with Schema Registry registration for TelemetryEvent."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from kafka import KafkaProducer

from ingestion.simulator.avro_codec import encode_confluent_avro, load_avro_schema

logger = logging.getLogger("argus.ingestion.simulator")


def ensure_schema_registered(
    schema_registry_url: str,
    subject: str,
    schema: dict[str, Any],
) -> int:
    """Register (or look up) an Avro schema; return schema id."""
    body = json.dumps(
        {"schemaType": "AVRO", "schema": json.dumps(schema)}
    ).encode()
    req = urllib.request.Request(
        f"{schema_registry_url.rstrip('/')}/subjects/{subject}/versions",
        data=body,
        headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
            schema_id = int(payload["id"])
            logger.info(
                "schema_registered",
                extra={"subject": subject, "schema_id": schema_id},
            )
            return schema_id
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"schema registry register failed ({exc.code}): {detail}"
        ) from exc


class TelemetryKafkaPublisher:
    """Publishes Avro TelemetryEvent (or raw corrupt bytes) to Kafka."""

    def __init__(
        self,
        *,
        brokers: str,
        topic: str,
        schema_registry_url: str,
        subject: str = "argus.telemetry.TelemetryEvent-value",
    ) -> None:
        self.topic = topic
        self.schema = load_avro_schema()
        self.schema_id = ensure_schema_registered(
            schema_registry_url, subject, self.schema
        )
        self._producer = KafkaProducer(
            bootstrap_servers=[b.strip() for b in brokers.split(",") if b.strip()],
            acks="all",
            linger_ms=20,
            retries=3,
        )

    def publish(
        self,
        *,
        key: str,
        record: dict[str, Any] | None,
        raw: bytes | None = None,
    ) -> None:
        if raw is not None:
            value = raw
        elif record is not None:
            value = encode_confluent_avro(
                record, schema=self.schema, schema_id=self.schema_id
            )
        else:
            raise ValueError("publish requires record or raw bytes")
        self._producer.send(self.topic, key=key.encode("utf-8"), value=value)

    def flush(self) -> None:
        self._producer.flush()

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()
