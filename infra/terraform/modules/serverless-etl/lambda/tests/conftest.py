"""Shared moto fixtures for ARGUS serverless ETL Lambda handlers."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import boto3
import pytest
from moto import mock_aws


BUCKET = "argus-iceberg-test"
GLUE_DATABASE = "fleet"
GLUE_TABLE = "serverless_batches"
REGION = "us-east-1"


def clean_telemetry_record(**overrides: Any) -> dict[str, Any]:
    """One TelemetryEvent-shaped row that passes validate_telemetry_batch."""
    row: dict[str, Any] = {
        "vehicle_id": "VH-0001234",
        "trip_id": "trip-test-1",
        "timestamp": datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc).isoformat(),
        "gps_lat": 40.44,
        "gps_lon": -79.99,
        "speed_mph": 35.0,
        "brake_pressure": 0.2,
        "lidar_temp_c": 42.0,
        "compute_load_pct": 55.0,
        "sensor_status": "SENSOR_STATUS_OK",
        "hardware_version": "hw-rev-3.2",
        "device_type": "DEVICE_TYPE_SIMULATOR",
    }
    row.update(overrides)
    return row


@pytest.fixture
def aws_env(monkeypatch: pytest.MonkeyPatch):
    """Credential + region env vars required by boto3/moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("LAKEHOUSE_BUCKET", BUCKET)
    monkeypatch.setenv("GLUE_DATABASE", GLUE_DATABASE)
    monkeypatch.setenv("GLUE_TABLE", GLUE_TABLE)
    monkeypatch.setenv("SERVERLESS_PREFIX", "serverless")


@pytest.fixture
def aws(aws_env):
    """Mocked S3 + Glue + SQS with a lakehouse bucket, Glue table, and DLQ."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET)

        glue = boto3.client("glue", region_name=REGION)
        glue.create_database(DatabaseInput={"Name": GLUE_DATABASE})
        glue.create_table(
            DatabaseName=GLUE_DATABASE,
            TableInput={
                "Name": GLUE_TABLE,
                "TableType": "EXTERNAL_TABLE",
                "StorageDescriptor": {
                    "Columns": [
                        {"Name": "vehicle_id", "Type": "string"},
                        {"Name": "trip_id", "Type": "string"},
                        {"Name": "timestamp", "Type": "timestamp"},
                        {"Name": "gps_lat", "Type": "double"},
                        {"Name": "gps_lon", "Type": "double"},
                        {"Name": "speed_mph", "Type": "double"},
                        {"Name": "brake_pressure", "Type": "double"},
                        {"Name": "lidar_temp_c", "Type": "double"},
                        {"Name": "compute_load_pct", "Type": "double"},
                        {"Name": "sensor_status", "Type": "string"},
                        {"Name": "hardware_version", "Type": "string"},
                        {"Name": "device_type", "Type": "string"},
                    ],
                    "Location": f"s3://{BUCKET}/serverless/telemetry/",
                    "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                    "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                    "SerdeInfo": {
                        "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
                    },
                },
                "PartitionKeys": [{"Name": "dt", "Type": "string"}],
            },
        )

        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName="argus-serverless-etl-dlq")["QueueUrl"]
        os.environ["DLQ_QUEUE_URL"] = queue_url

        yield {
            "s3": s3,
            "glue": glue,
            "sqs": sqs,
            "bucket": BUCKET,
            "queue_url": queue_url,
            "database": GLUE_DATABASE,
            "table": GLUE_TABLE,
        }
