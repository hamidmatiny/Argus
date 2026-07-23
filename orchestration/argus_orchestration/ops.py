"""Ops: trigger_retraining — MLflow lineage + Kafka event (replaces webhook)."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dagster import OpExecutionContext, graph, op

from argus_orchestration.config import (
    DRIFT_REPORTS_DIR,
    RETRAIN_MAX_SCORE_THRESHOLD,
    RETRAIN_MIN_DRIFTED_FEATURES,
    RETRAINING_TOPIC,
)
from argus_orchestration.logic.drift_decision import (
    decide_retraining,
    load_latest_drift_signal,
)
from argus_orchestration.resources import KafkaPublisherResource, MLflowResource


@op(description="Evaluate Evidently sidecars into a structured retrain decision.")
def build_retrain_decision(context: OpExecutionContext) -> dict[str, Any]:
    signal = load_latest_drift_signal(Path(DRIFT_REPORTS_DIR))
    decision = decide_retraining(
        signal,
        max_score_threshold=RETRAIN_MAX_SCORE_THRESHOLD,
        min_drifted_features=RETRAIN_MIN_DRIFTED_FEATURES,
    )
    context.log.info(
        "decision=%s reason=%s max_score=%.4f",
        decision["should_retrain"],
        decision["reason"],
        decision["max_drift_score"],
    )
    return decision


@op(
    description=(
        "When should_retrain, log an MLflow run and publish "
        "orchestration.retraining_triggered (real lineage vs sentinel-ray webhook)."
    ),
)
def trigger_retraining(
    context: OpExecutionContext,
    decision: dict[str, Any],
    mlflow: MLflowResource,
    kafka: KafkaPublisherResource,
) -> dict[str, Any]:
    if not decision.get("should_retrain"):
        context.log.info("skip_retrain reason=%s", decision.get("reason"))
        return {
            "triggered": False,
            "reason": decision.get("reason"),
            "mlflow_run_id": None,
            "kafka_topic": RETRAINING_TOPIC,
        }

    trigger_id = f"retrain-{uuid.uuid4().hex[:12]}"
    params = {
        "trigger_id": trigger_id,
        "trigger_reason": str(decision.get("reason")),
        "source_report": str(decision.get("source_report") or ""),
        "window_size": int(decision.get("window_size") or 0),
    }
    metrics: dict[str, float] = {
        "max_drift_score": float(decision.get("max_drift_score") or 0.0),
        "drifted_feature_count": float(decision.get("drifted_feature_count") or 0),
    }
    for feature, score in list((decision.get("feature_scores") or {}).items())[:20]:
        metrics[f"drift_{feature}"] = float(score)

    run_id = mlflow.log_retraining_run(params=params, metrics=metrics)
    event = {
        "event_type": "retraining_triggered",
        "trigger_id": trigger_id,
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": decision.get("reason"),
        "max_drift_score": decision.get("max_drift_score"),
        "drifted_feature_count": decision.get("drifted_feature_count"),
        "feature_scores": decision.get("feature_scores"),
        "window_size": decision.get("window_size"),
        "source_report": decision.get("source_report"),
        "mlflow_tracking_uri": mlflow.tracking_uri,
        "mlflow_experiment": mlflow.experiment_name,
    }
    kafka.publish(event)
    context.log.warning(
        "retraining_triggered trigger_id=%s mlflow_run_id=%s topic=%s",
        trigger_id,
        run_id,
        RETRAINING_TOPIC,
    )
    return {
        "triggered": True,
        "trigger_id": trigger_id,
        "mlflow_run_id": run_id,
        "kafka_topic": RETRAINING_TOPIC,
        "event": event,
    }


@graph(description="Evidently drift signal → decision → MLflow + Kafka")
def drift_to_retrain_graph():
    trigger_retraining(build_retrain_decision())
