"""Validate raw batch with shared Pandera gate; stage Parquet + dead-letter rejects."""

from __future__ import annotations

import json
from typing import Any

import awswrangler as wr
import boto3
import pandas as pd
from pandera.errors import SchemaError, SchemaErrors

from common import require_env, require_event_key, serverless_prefix
from v1.pandera_schemas import TELEMETRY_EVENT_SCHEMA, validate_telemetry_batch


def _triage_batch(records: list[Any]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Triage each record using the same Pandera schema / validate_telemetry_batch
    the real-time pipeline uses — do not reimplement field checks here.
    """
    valid_frames: list[pd.DataFrame] = []
    rejected: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            rejected.append(
                {
                    "record": {"value": record},
                    "rejection_reason": f"record at index {index} is not an object",
                    "corruption_type": "invalid_record_type",
                }
            )
            continue

        frame = pd.DataFrame([record])
        try:
            validated = validate_telemetry_batch(frame)
            valid_frames.append(validated)
        except (SchemaError, SchemaErrors) as exc:
            rejected.append(
                {
                    "record": record,
                    "rejection_reason": str(exc),
                    "corruption_type": "pandera_schema_error",
                }
            )
        except Exception as exc:  # noqa: BLE001 — surface unexpected validation failures to DLQ path
            rejected.append(
                {
                    "record": record,
                    "rejection_reason": str(exc),
                    "corruption_type": "validation_error",
                }
            )

    if valid_frames:
        return pd.concat(valid_frames, ignore_index=True), rejected
    return pd.DataFrame(columns=list(TELEMETRY_EVENT_SCHEMA.columns.keys())), rejected


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    raw_key = require_event_key(event, "raw_key")
    execution_id = require_event_key(event, "execution_id")
    bucket = require_env("LAKEHOUSE_BUCKET")
    prefix = serverless_prefix()

    s3 = boto3.client("s3")
    payload = json.loads(s3.get_object(Bucket=bucket, Key=raw_key)["Body"].read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Raw batch must be a JSON array.")

    total_count = len(payload)
    passing_frame, rejected_rows = _triage_batch(payload)
    valid_count = len(passing_frame)
    rejected_count = len(rejected_rows)
    rejection_rate = (rejected_count / total_count) if total_count else 0.0

    staging_key = f"{prefix}/staging/{execution_id}/validated.parquet"
    staging_uri = f"s3://{bucket}/{staging_key}"
    wr.s3.to_parquet(df=passing_frame, path=staging_uri, index=False, compression="snappy")

    rejected_key = f"{prefix}/dead_letter/{execution_id}/rejected.json"
    s3.put_object(
        Bucket=bucket,
        Key=rejected_key,
        Body=json.dumps(rejected_rows, default=str),
        ContentType="application/json",
    )

    return {
        "staging_key": staging_key,
        "rejection_rate": rejection_rate,
        "valid_count": valid_count,
        "rejected_count": rejected_count,
        "execution_id": execution_id,
        "total_count": total_count,
        "rejected_key": rejected_key,
    }
