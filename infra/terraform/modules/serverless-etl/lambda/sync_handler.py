"""Promote staging Parquet to serverless/telemetry and register a Glue partition."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import awswrangler as wr
import boto3
import pandas as pd
from botocore.exceptions import ClientError

from common import require_env, require_event_key, serverless_prefix


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Write serverless/telemetry/dt=<date>/{execution_id}.parquet and register the
    partition on fleet.serverless_batches — never fleet.telemetry / Iceberg warehouse.
    """
    staging_key = require_event_key(event, "staging_key")
    execution_id = require_event_key(event, "execution_id")
    bucket = require_env("LAKEHOUSE_BUCKET")
    glue_database = require_env("GLUE_DATABASE")
    glue_table = require_env("GLUE_TABLE")
    prefix = serverless_prefix()

    partition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    final_key = f"{prefix}/telemetry/dt={partition_date}/{execution_id}.parquet"
    final_uri = f"s3://{bucket}/{final_key}"
    staging_uri = f"s3://{bucket}/{staging_key}"

    s3 = boto3.client("s3")
    s3.copy_object(
        Bucket=bucket,
        Key=final_key,
        CopySource={"Bucket": bucket, "Key": staging_key},
    )

    frame = wr.s3.read_parquet(path=staging_uri)
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(frame)

    _ensure_partition(
        database=glue_database,
        table=glue_table,
        bucket=bucket,
        partition_date=partition_date,
        prefix=prefix,
    )

    return {
        "final_key": final_key,
        "final_uri": final_uri,
        "glue_table": f"{glue_database}.{glue_table}",
        "partitions_added": [f"dt={partition_date}"],
        "execution_id": execution_id,
        "rows_synced": len(frame),
    }


def _ensure_partition(
    *,
    database: str,
    table: str,
    bucket: str,
    partition_date: str,
    prefix: str,
) -> None:
    glue = boto3.client("glue")
    location = f"s3://{bucket}/{prefix}/telemetry/dt={partition_date}/"
    try:
        glue.get_partition(
            DatabaseName=database,
            TableName=table,
            PartitionValues=[partition_date],
        )
        return
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "EntityNotFoundException":
            raise

    table_meta = glue.get_table(DatabaseName=database, Name=table)["Table"]
    storage = table_meta["StorageDescriptor"]
    partition_sd = {
        **storage,
        "Location": location,
    }
    glue.create_partition(
        DatabaseName=database,
        TableName=table,
        PartitionInput={
            "Values": [partition_date],
            "StorageDescriptor": partition_sd,
        },
    )
