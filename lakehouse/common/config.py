"""Lakehouse configuration (Iceberg REST / Glue, MinIO / S3, Kafka)."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:19092")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:18081")

VALIDATED_TOPIC = os.getenv("LAKEHOUSE_VALIDATED_TOPIC", "telemetry.validated")
QUARANTINE_TOPIC = os.getenv("LAKEHOUSE_QUARANTINE_TOPIC", "telemetry.quarantine")
WRITER_GROUP_ID = os.getenv("LAKEHOUSE_WRITER_GROUP_ID", "argus-lakehouse-writer")
DLQ_GROUP_ID = os.getenv("LAKEHOUSE_DLQ_GROUP_ID", "argus-lakehouse-dlq-writer")

# rest (local) | glue (prod continuity with hydra-data-factory)
CATALOG_TYPE = os.getenv("ICEBERG_CATALOG_TYPE", "rest").lower()
CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://localhost:8181")
CATALOG_NAME = os.getenv("ICEBERG_CATALOG_NAME", "argus")
WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://warehouse/")
NAMESPACE = os.getenv("ICEBERG_NAMESPACE", "fleet")
TELEMETRY_TABLE = os.getenv("ICEBERG_TELEMETRY_TABLE", "telemetry")
QUARANTINE_TABLE = os.getenv("ICEBERG_QUARANTINE_TABLE", "quarantine")

# S3 / MinIO
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", os.getenv("S3_ACCESS_KEY", "admin"))
S3_SECRET_KEY = os.getenv(
    "AWS_SECRET_ACCESS_KEY", os.getenv("S3_SECRET_KEY", "password")
)
S3_REGION = os.getenv("AWS_REGION", os.getenv("S3_REGION", "us-east-1"))
S3_PATH_STYLE = os.getenv("S3_PATH_STYLE_ACCESS", "true").lower() in {
    "1",
    "true",
    "yes",
}

# Glue (prod)
GLUE_REGION = os.getenv("GLUE_REGION", S3_REGION)
GLUE_DATABASE = os.getenv("GLUE_DATABASE", NAMESPACE)

BATCH_SIZE = int(os.getenv("LAKEHOUSE_BATCH_SIZE", "50"))
FLUSH_INTERVAL_SEC = float(os.getenv("LAKEHOUSE_FLUSH_INTERVAL_SEC", "5.0"))

WRITER_HEALTH_PORT = int(os.getenv("LAKEHOUSE_WRITER_HEALTH_PORT", "8096"))
DLQ_HEALTH_PORT = int(os.getenv("LAKEHOUSE_DLQ_HEALTH_PORT", "8097"))

PARQUET_COMPRESSION = os.getenv("LAKEHOUSE_PARQUET_COMPRESSION", "snappy")
