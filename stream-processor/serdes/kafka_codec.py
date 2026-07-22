"""Kafka / Avro helpers for the stream processor (reuse ingestion codecs)."""

from __future__ import annotations

import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Allow importing ingestion codecs when running from repo root / container.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ingestion.simulator.avro_codec import (  # noqa: E402
    decode_confluent_avro,
    encode_confluent_avro,
    load_avro_schema,
)

logger = logging.getLogger("argus.stream_processor")


def ensure_schema_registered(
    schema_registry_url: str,
    subject: str,
    schema: dict[str, Any],
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
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return int(json.loads(resp.read().decode())["id"])
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"schema registry register failed ({exc.code}): {detail}"
        ) from exc


def decode_value(value: bytes) -> tuple[dict[str, Any] | None, str]:
    schema = load_avro_schema()
    try:
        _, record = decode_confluent_avro(value, schema=schema)
        return record, "avro"
    except Exception:
        pass
    try:
        record = json.loads(value.decode("utf-8"))
        if isinstance(record, dict):
            return record, "json"
    except Exception:
        pass
    return None, "raw"


def encode_telemetry(record: dict[str, Any], *, schema_id: int) -> bytes:
    return encode_confluent_avro(
        record, schema=load_avro_schema(), schema_id=schema_id
    )


def encode_json(record: dict[str, Any]) -> bytes:
    return json.dumps(record, default=str).encode("utf-8")
