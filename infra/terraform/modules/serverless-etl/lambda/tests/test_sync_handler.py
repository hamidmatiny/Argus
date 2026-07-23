"""Tests for sync_handler — Parquet promote + idempotent Glue partition."""

from __future__ import annotations

from datetime import datetime, timezone

import awswrangler as wr
import pandas as pd
import pytest

from sync_handler import lambda_handler
from tests.conftest import clean_telemetry_record


def _seed_staging(aws, execution_id: str) -> str:
    staging_key = f"serverless/staging/{execution_id}/validated.parquet"
    frame = pd.DataFrame([clean_telemetry_record(), clean_telemetry_record(trip_id="t2")])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    wr.s3.to_parquet(
        df=frame,
        path=f"s3://{aws['bucket']}/{staging_key}",
        index=False,
        compression="snappy",
    )
    return staging_key


def test_sync_writes_parquet_and_partition_idempotently(aws):
    execution_id = "exec-sync-1"
    staging_key = _seed_staging(aws, execution_id)
    event = {"staging_key": staging_key, "execution_id": execution_id}

    first = lambda_handler(event, context=None)
    partition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    final_key = f"serverless/telemetry/dt={partition_date}/{execution_id}.parquet"

    assert first["final_key"] == final_key
    assert first["rows_synced"] == 2
    assert first["glue_table"] == "fleet.serverless_batches"
    assert first["partitions_added"] == [f"dt={partition_date}"]

    head = aws["s3"].head_object(Bucket=aws["bucket"], Key=final_key)
    assert head["ContentLength"] > 0

    part = aws["glue"].get_partition(
        DatabaseName=aws["database"],
        TableName=aws["table"],
        PartitionValues=[partition_date],
    )
    assert part["Partition"]["Values"] == [partition_date]

    # Second call must not raise (get_partition short-circuit).
    second = lambda_handler(event, context=None)
    assert second["rows_synced"] == 2
    assert second["final_key"] == final_key

    aws["glue"].get_partition(
        DatabaseName=aws["database"],
        TableName=aws["table"],
        PartitionValues=[partition_date],
    )


def test_sync_requires_staging_key(aws):
    with pytest.raises(ValueError, match="staging_key"):
        lambda_handler({"execution_id": "x"}, context=None)
