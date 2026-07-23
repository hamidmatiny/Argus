"""Ops: trigger_retraining — MLflow lineage + Kafka event (replaces webhook)."""

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dagster import In, OpExecutionContext, Out, graph, op

from argus_orchestration.config import (
    DRIFT_REPORTS_DIR,
    RETRAIN_MAX_SCORE_THRESHOLD,
    RETRAIN_MIN_DRIFTED_FEATURES,
    RETRAINING_TOPIC,
    SEED_SYNTHETIC_FROM_DRIFT,
    SYNTHETIC_SCENARIO_FRAMES,
)
from argus_orchestration.logic.drift_decision import (
    decide_retraining,
    load_latest_drift_signal,
)
from argus_orchestration.resources import KafkaPublisherResource, MLflowResource

# simulation/ sits next to orchestration/ in the monorepo.
_SIM_ROOT = Path(__file__).resolve().parents[2] / "simulation"
if str(_SIM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SIM_ROOT))
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


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
        "Optional: seed scenario_runner from the drift signature "
        "(brake_pressure / speed_mph) to produce targeted synthetic training data. "
        "Skipped when ORCH_SEED_SYNTHETIC_FROM_DRIFT=false or should_retrain=false."
    ),
    out=Out(dict),
)
def seed_synthetic_scenarios_from_incident(
    context: OpExecutionContext,
    decision: dict[str, Any],
) -> dict[str, Any]:
    if not SEED_SYNTHETIC_FROM_DRIFT:
        context.log.info("synthetic_seed skipped (ORCH_SEED_SYNTHETIC_FROM_DRIFT=false)")
        return {"seeded": False, "reason": "disabled"}

    if not decision.get("should_retrain"):
        context.log.info("synthetic_seed skipped (should_retrain=false)")
        return {"seeded": False, "reason": "no_retrain"}

    from argus_pipeline.incident_seeding import scenario_params_from_drift_decision
    from argus_pipeline.runner import run_pipeline

    params = scenario_params_from_drift_decision(
        decision, n_frames=SYNTHETIC_SCENARIO_FRAMES
    )
    artifacts = Path(os.getenv("ORCH_ARTIFACTS_DIR", "artifacts"))
    warehouse = artifacts / "sim_warehouse"
    warehouse.mkdir(parents=True, exist_ok=True)
    sqlite_path = artifacts / "sim_catalog.db"

    config = {
        **params,
        "catalog_type": "sqlite",
        "warehouse": f"file://{warehouse}",
        "sqlite_path": str(sqlite_path),
        "base_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    context.log.info(
        "synthetic_seed scenario_type=%s n_frames=%s signature=%s",
        params["scenario_type"],
        params["n_frames"],
        params["drift_signature"],
    )
    result = run_pipeline(config)
    return {
        "seeded": True,
        "scenario_type": params["scenario_type"],
        "drift_signature": params["drift_signature"],
        "batch_sizes": result["batch_sizes"],
        "sinks": result["sinks"],
    }


@op(
    description=(
        "When should_retrain, log an MLflow run and publish "
        "orchestration.retraining_triggered (real lineage vs sentinel-ray webhook)."
    ),
    ins={
        "decision": In(dict),
        "seed_result": In(dict),
    },
)
def trigger_retraining(
    context: OpExecutionContext,
    decision: dict[str, Any],
    seed_result: dict[str, Any],
    mlflow: MLflowResource,
    kafka: KafkaPublisherResource,
) -> dict[str, Any]:
    # seed_result orders this op after optional synthetic seeding (not required for retrain).
    if seed_result.get("seeded"):
        context.log.info(
            "synthetic_seed_complete scenario_type=%s",
            seed_result.get("scenario_type"),
        )

    if not decision.get("should_retrain"):
        context.log.info("skip_retrain reason=%s", decision.get("reason"))
        return {
            "triggered": False,
            "reason": decision.get("reason"),
            "mlflow_run_id": None,
            "kafka_topic": RETRAINING_TOPIC,
            "synthetic_seed": seed_result,
        }

    trigger_id = f"retrain-{uuid.uuid4().hex[:12]}"
    params = {
        "trigger_id": trigger_id,
        "trigger_reason": str(decision.get("reason")),
        "source_report": str(decision.get("source_report") or ""),
        "window_size": int(decision.get("window_size") or 0),
        "synthetic_seeded": str(bool(seed_result.get("seeded"))),
        "synthetic_scenario_type": str(seed_result.get("scenario_type") or ""),
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
        "synthetic_seed": seed_result,
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
        "synthetic_seed": seed_result,
    }


@graph(description="Evidently drift signal → optional synthetic seed → MLflow + Kafka")
def drift_to_retrain_graph():
    decision = build_retrain_decision()
    seed = seed_synthetic_scenarios_from_incident(decision)
    trigger_retraining(decision, seed)
