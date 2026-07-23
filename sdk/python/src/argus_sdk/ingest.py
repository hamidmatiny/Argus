"""Kafka ingest client — validates TelemetryEvent then publishes to telemetry.raw."""

from __future__ import annotations

import json
import os
import struct
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path
from typing import Any

from argus_sdk.models import TelemetryEvent


def _load_schema() -> dict[str, Any]:
    env = os.environ.get("ARGUS_AVRO_SCHEMA_PATH")
    if env:
        return json.loads(Path(env).read_text())
    # Packaged copy (hatch force-include) or monorepo shared/avro.
    try:
        root = resources.files("argus_sdk") / "data" / "telemetry_event.avsc"
        return json.loads(root.read_text())
    except (FileNotFoundError, TypeError, ModuleNotFoundError, OSError):
        pass
    repo = (
        Path(__file__).resolve().parents[4] / "shared" / "avro" / "telemetry_event.avsc"
    )
    if repo.is_file():
        return json.loads(repo.read_text())
    raise FileNotFoundError(
        "telemetry_event.avsc not found; set ARGUS_AVRO_SCHEMA_PATH or install with package data"
    )


def encode_confluent_avro(
    record: dict[str, Any], *, schema: dict[str, Any], schema_id: int
) -> bytes:
    import io

    import fastavro

    parsed = fastavro.parse_schema(schema)
    buf = io.BytesIO()
    fastavro.schemaless_writer(buf, parsed, record)
    return b"\x00" + struct.pack(">I", schema_id) + buf.getvalue()


def ensure_schema_registered(
    schema_registry_url: str, subject: str, schema: dict[str, Any]
) -> int:
    body = json.dumps(
        {"schemaType": "AVRO", "schema": json.dumps(schema)}
    ).encode()
    req = urllib.request.Request(
        f"{schema_registry_url.rstrip('/')}/subjects/{subject}/versions",
        data=body,
        headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode())
        return int(payload["id"])


class IngestClient:
    """Drop-in producer for third-party apps.

    Example::

        from argus_sdk import IngestClient, TelemetryEvent, DeviceType, SensorStatus
        with IngestClient() as ingest:
            ingest.publish(TelemetryEvent(...))
    """

    def __init__(
        self,
        *,
        brokers: str | None = None,
        topic: str | None = None,
        schema_registry_url: str | None = None,
        subject: str = "argus.telemetry.TelemetryEvent-value",
        schema_id: int | None = None,
    ) -> None:
        try:
            from kafka import KafkaProducer
        except ImportError as exc:
            raise ImportError(
                "IngestClient requires the ingest extra: pip install 'argus-sdk[ingest]'"
            ) from exc

        self.topic = topic or os.environ.get("ARGUS_TELEMETRY_TOPIC", "telemetry.raw")
        self.schema = _load_schema()
        registry = schema_registry_url or os.environ.get(
            "ARGUS_SCHEMA_REGISTRY_URL", "http://localhost:18081"
        )
        if schema_id is not None:
            self.schema_id = schema_id
        else:
            try:
                self.schema_id = ensure_schema_registered(registry, subject, self.schema)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
                # Local demos often already registered schema id 1.
                self.schema_id = int(os.environ.get("ARGUS_SCHEMA_ID", "1"))

        brokers = brokers or os.environ.get("ARGUS_KAFKA_BROKERS", "localhost:19092")
        self._producer = KafkaProducer(
            bootstrap_servers=[b.strip() for b in brokers.split(",") if b.strip()],
            acks="all",
            linger_ms=20,
            retries=3,
        )

    def publish(self, event: TelemetryEvent | dict[str, Any]) -> None:
        if isinstance(event, dict):
            event = TelemetryEvent.model_validate(event)
        record = event.to_avro_record()
        value = encode_confluent_avro(
            record, schema=self.schema, schema_id=self.schema_id
        )
        self._producer.send(
            self.topic, key=event.vehicle_id.encode("utf-8"), value=value
        )

    def flush(self) -> None:
        self._producer.flush()

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()

    def __enter__(self) -> IngestClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
