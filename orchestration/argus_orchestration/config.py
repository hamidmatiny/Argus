"""Orchestration configuration."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = Path(os.getenv("ORCH_ARTIFACTS_DIR", str(PACKAGE_ROOT / "artifacts")))
DRIFT_REPORTS_DIR = Path(
    os.getenv("DRIFT_REPORTS_DIR", str(PACKAGE_ROOT.parent / "drift-monitor" / "reports"))
)
FEATURE_STORE_DIR = Path(
    os.getenv("FEAST_REPO_PATH", str(PACKAGE_ROOT / "feature_store"))
)

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:19092")
RETRAINING_TOPIC = os.getenv(
    "ORCH_RETRAINING_TOPIC", "orchestration.retraining_triggered"
)

ICEBERG_CATALOG_TYPE = os.getenv("ICEBERG_CATALOG_TYPE", "rest")
ICEBERG_CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://localhost:8181")
ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://warehouse/")
ICEBERG_NAMESPACE = os.getenv("ICEBERG_NAMESPACE", "fleet")
TELEMETRY_TABLE = os.getenv("ICEBERG_TELEMETRY_TABLE", "telemetry")
QUARANTINE_TABLE = os.getenv("ICEBERG_QUARANTINE_TABLE", "quarantine")

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", os.getenv("S3_ACCESS_KEY", "admin"))
S3_SECRET_KEY = os.getenv(
    "AWS_SECRET_ACCESS_KEY", os.getenv("S3_SECRET_KEY", "password")
)
S3_REGION = os.getenv("AWS_REGION", "us-east-1")

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5002")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT_NAME", "argus-retraining")

# Retrain when max Evidently/KS drift score exceeds this, or drifted feature count.
RETRAIN_MAX_SCORE_THRESHOLD = float(os.getenv("ORCH_RETRAIN_MAX_SCORE_THRESHOLD", "0.5"))
RETRAIN_MIN_DRIFTED_FEATURES = int(os.getenv("ORCH_RETRAIN_MIN_DRIFTED_FEATURES", "2"))

FEATURES = (
    "speed_mph",
    "brake_pressure",
    "lidar_temp_c",
    "compute_load_pct",
)
