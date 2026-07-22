"""Avro encode/decode helpers for TelemetryEvent (Confluent wire format)."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import fastavro

# Repo-root-relative default; override via ARGUS_AVRO_SCHEMA_PATH.
_DEFAULT_SCHEMA = (
    Path(__file__).resolve().parents[2] / "shared" / "avro" / "telemetry_event.avsc"
)


def load_avro_schema(path: Path | None = None) -> dict[str, Any]:
    schema_path = path or Path(
        __import__("os").environ.get("ARGUS_AVRO_SCHEMA_PATH", str(_DEFAULT_SCHEMA))
    )
    return json.loads(schema_path.read_text())


def encode_confluent_avro(
    record: dict[str, Any],
    *,
    schema: dict[str, Any],
    schema_id: int,
) -> bytes:
    """Magic byte 0 + big-endian schema id + schemaless Avro payload."""
    import io

    parsed = fastavro.parse_schema(schema)
    buf = io.BytesIO()
    fastavro.schemaless_writer(buf, parsed, record)
    return b"\x00" + struct.pack(">I", schema_id) + buf.getvalue()


def decode_confluent_avro(
    data: bytes,
    *,
    schema: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Decode Confluent wire-format Avro; returns (schema_id, record)."""
    import io

    if len(data) < 5 or data[0] != 0:
        raise ValueError("not confluent-avro wire format")
    schema_id = struct.unpack(">I", data[1:5])[0]
    parsed = fastavro.parse_schema(schema)
    record = fastavro.schemaless_reader(io.BytesIO(data[5:]), parsed)
    return schema_id, dict(record)
