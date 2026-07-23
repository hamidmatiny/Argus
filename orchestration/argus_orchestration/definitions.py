"""Dagster Definitions entrypoint (workspace module)."""

from __future__ import annotations

from dagster import Definitions

from argus_orchestration.assets import (
    daily_feature_statistics,
    retrain_decision,
    weekly_quarantine_audit,
)
from argus_orchestration.ops import drift_to_retrain_graph
from argus_orchestration.resources import (
    IcebergTelemetryResource,
    KafkaPublisherResource,
    MLflowResource,
)
from argus_orchestration.schedules import (
    daily_feature_stats_job,
    daily_feature_stats_schedule,
    drift_decision_job,
    hourly_drift_decision_schedule,
    weekly_quarantine_audit_job,
    weekly_quarantine_audit_schedule,
)

iceberg_resource = IcebergTelemetryResource()
mlflow_resource = MLflowResource()
kafka_resource = KafkaPublisherResource()

drift_retrain_job = drift_to_retrain_graph.to_job(
    name="drift_retrain_job",
    description=(
        "Replace sentinel-ray retraining webhook: decide from Evidently → "
        "MLflow run + Kafka orchestration.retraining_triggered"
    ),
    resource_defs={
        "mlflow": mlflow_resource,
        "kafka": kafka_resource,
    },
)

defs = Definitions(
    assets=[
        daily_feature_statistics,
        retrain_decision,
        weekly_quarantine_audit,
    ],
    jobs=[
        daily_feature_stats_job,
        weekly_quarantine_audit_job,
        drift_decision_job,
        drift_retrain_job,
    ],
    schedules=[
        daily_feature_stats_schedule,
        weekly_quarantine_audit_schedule,
        hourly_drift_decision_schedule,
    ],
    resources={
        "iceberg": iceberg_resource,
        "mlflow": mlflow_resource,
        "kafka": kafka_resource,
    },
)
