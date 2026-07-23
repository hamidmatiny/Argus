"""Tests for validate_handler — real Pandera gate triage."""

from __future__ import annotations

import json

import awswrangler as wr
import pandas as pd

from tests.conftest import clean_telemetry_record
from validate_handler import lambda_handler


def _put_raw_batch(aws, execution_id: str, records: list[dict]) -> str:
    key = f"serverless/raw/{execution_id}/batch.json"
    aws["s3"].put_object(
        Bucket=aws["bucket"],
        Key=key,
        Body=json.dumps(records, default=str),
        ContentType="application/json",
    )
    return key


def test_validate_accepts_clean_batch(aws):
    execution_id = "exec-val-clean"
    raw_key = _put_raw_batch(
        aws,
        execution_id,
        [clean_telemetry_record(), clean_telemetry_record(vehicle_id="VH-0005678", trip_id="t2")],
    )

    result = lambda_handler(
        {"raw_key": raw_key, "execution_id": execution_id},
        context=None,
    )

    assert result["valid_count"] == 2
    assert result["rejected_count"] == 0
    assert result["rejection_rate"] == 0.0
    assert result["staging_key"] == f"serverless/staging/{execution_id}/validated.parquet"

    frame = wr.s3.read_parquet(path=f"s3://{aws['bucket']}/{result['staging_key']}")
    assert isinstance(frame, pd.DataFrame)
    assert len(frame) == 2

    rejected = json.loads(
        aws["s3"]
        .get_object(Bucket=aws["bucket"], Key=result["rejected_key"])["Body"]
        .read()
    )
    assert rejected == []


def test_validate_rejects_out_of_range_speed(aws):
    execution_id = "exec-val-reject"
    raw_key = _put_raw_batch(
        aws,
        execution_id,
        [
            clean_telemetry_record(),
            clean_telemetry_record(speed_mph=200.0, trip_id="bad-speed"),
        ],
    )

    result = lambda_handler(
        {"raw_key": raw_key, "execution_id": execution_id},
        context=None,
    )

    assert result["total_count"] == 2
    assert result["valid_count"] == 1
    assert result["rejected_count"] == 1
    assert result["rejection_rate"] == 0.5

    frame = wr.s3.read_parquet(path=f"s3://{aws['bucket']}/{result['staging_key']}")
    assert len(frame) == 1

    rejected = json.loads(
        aws["s3"]
        .get_object(Bucket=aws["bucket"], Key=result["rejected_key"])["Body"]
        .read()
    )
    assert len(rejected) == 1
    assert rejected[0]["corruption_type"] == "pandera_schema_error"
    assert "speed" in rejected[0]["rejection_reason"].lower()
