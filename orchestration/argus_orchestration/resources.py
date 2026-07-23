"""Dagster resources: Iceberg readers, Kafka publisher, MLflow."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import ConfigurableResource

from argus_orchestration.config import (
    ICEBERG_CATALOG_TYPE,
    ICEBERG_CATALOG_URI,
    ICEBERG_NAMESPACE,
    ICEBERG_WAREHOUSE,
    KAFKA_BROKERS,
    MLFLOW_EXPERIMENT,
    MLFLOW_TRACKING_URI,
    QUARANTINE_TABLE,
    RETRAINING_TOPIC,
    S3_ACCESS_KEY,
    S3_ENDPOINT,
    S3_REGION,
    S3_SECRET_KEY,
    TELEMETRY_TABLE,
)

logger = logging.getLogger("argus.orchestration.resources")


class IcebergTelemetryResource(ConfigurableResource):
    """Load fleet.telemetry / fleet.quarantine via PyIceberg (or fixture override)."""

    catalog_type: str = ICEBERG_CATALOG_TYPE
    catalog_uri: str = ICEBERG_CATALOG_URI
    warehouse: str = ICEBERG_WAREHOUSE
    namespace: str = ICEBERG_NAMESPACE
    telemetry_table: str = TELEMETRY_TABLE
    quarantine_table: str = QUARANTINE_TABLE
    # Optional CSV/Parquet path for tests / offline demos.
    fixture_telemetry_path: str = ""
    fixture_quarantine_path: str = ""

    def _catalog(self):
        from pyiceberg.catalog import load_catalog

        conf: dict[str, Any] = {
            "type": self.catalog_type,
            "uri": self.catalog_uri,
            "warehouse": self.warehouse,
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": S3_ACCESS_KEY,
            "s3.secret-access-key": S3_SECRET_KEY,
            "s3.region": S3_REGION,
            "s3.path-style-access": "true",
            "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
        }
        return load_catalog("argus", **conf)

    def load_telemetry(self, *, limit: int | None = 50_000) -> pd.DataFrame:
        if self.fixture_telemetry_path:
            path = Path(self.fixture_telemetry_path)
            if path.suffix == ".parquet":
                return pd.read_parquet(path)
            return pd.read_csv(path)
        table = self._catalog().load_table(
            f"{self.namespace}.{self.telemetry_table}"
        )
        arrow = table.scan().to_arrow()
        df = arrow.to_pandas()
        if limit is not None and len(df) > limit:
            return df.tail(limit).reset_index(drop=True)
        return df

    def load_quarantine(self, *, limit: int | None = 50_000) -> pd.DataFrame:
        if self.fixture_quarantine_path:
            path = Path(self.fixture_quarantine_path)
            if path.suffix == ".parquet":
                return pd.read_parquet(path)
            return pd.read_csv(path)
        table = self._catalog().load_table(
            f"{self.namespace}.{self.quarantine_table}"
        )
        arrow = table.scan().to_arrow()
        df = arrow.to_pandas()
        if limit is not None and len(df) > limit:
            return df.tail(limit).reset_index(drop=True)
        return df


class KafkaPublisherResource(ConfigurableResource):
    brokers: str = KAFKA_BROKERS
    topic: str = RETRAINING_TOPIC

    def publish(self, event: dict[str, Any]) -> None:
        from kafka import KafkaProducer

        producer = KafkaProducer(
            bootstrap_servers=[b.strip() for b in self.brokers.split(",") if b.strip()],
            acks="all",
            client_id="argus-orchestration",
        )
        try:
            producer.send(
                self.topic,
                key=str(event.get("run_id") or event.get("trigger_id") or "").encode(),
                value=json.dumps(event, default=str).encode("utf-8"),
                headers=[("content-type", b"application/json")],
            )
            producer.flush()
        finally:
            producer.close()


class MLflowResource(ConfigurableResource):
    tracking_uri: str = MLFLOW_TRACKING_URI
    experiment_name: str = MLFLOW_EXPERIMENT

    def log_retraining_run(
        self, *, params: dict[str, Any], metrics: dict[str, float]
    ) -> str:
        import mlflow

        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment_name)
        with mlflow.start_run(run_name="argus-retrain-trigger") as run:
            for key, value in params.items():
                mlflow.log_param(key, value if value is not None else "")
            for key, value in metrics.items():
                mlflow.log_metric(key, float(value))
            mlflow.set_tag("source", "argus-orchestration")
            mlflow.set_tag("event", "retraining_triggered")
            return str(run.info.run_id)
