"""Dagster software-defined assets for ARGUS MLOps loop."""

import json
from pathlib import Path
from typing import Any

from dagster import (
    AssetExecutionContext,
    AssetKey,
    MetadataValue,
    MaterializeResult,
    asset,
)

from argus_orchestration.config import (
    ARTIFACTS_DIR,
    DRIFT_REPORTS_DIR,
    FEATURE_STORE_DIR,
    RETRAIN_MAX_SCORE_THRESHOLD,
    RETRAIN_MIN_DRIFTED_FEATURES,
)
from argus_orchestration.logic.drift_decision import (
    decide_retraining,
    load_latest_drift_signal,
)
from argus_orchestration.logic.feature_stats import compute_feature_statistics
from argus_orchestration.logic.quarantine_audit import summarize_quarantine
from argus_orchestration.resources import IcebergTelemetryResource


@asset(
    key=AssetKey(["lakehouse", "daily_feature_statistics"]),
    group_name="lakehouse_mlops",
    compute_kind="pandas",
    description=(
        "Daily feature statistics (mean/std/p50/p95) per device_type over "
        "Iceberg fleet.telemetry — feeds Feast and drift context."
    ),
)
def daily_feature_statistics(
    context: AssetExecutionContext,
    iceberg: IcebergTelemetryResource,
) -> MaterializeResult:
    telemetry = iceberg.load_telemetry()
    context.log.info("loaded telemetry rows=%s", len(telemetry))
    stats = compute_feature_statistics(telemetry)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_parquet = ARTIFACTS_DIR / "daily_feature_statistics.parquet"
    out_json = ARTIFACTS_DIR / "daily_feature_statistics.json"
    stats.to_parquet(out_parquet, index=False)
    if stats.empty:
        out_json.write_text("[]", encoding="utf-8")
    else:
        payload = stats.copy()
        if "computed_at" in payload.columns:
            payload["computed_at"] = payload["computed_at"].astype(str)
        out_json.write_text(
            payload.to_json(orient="records", date_format="iso"),
            encoding="utf-8",
        )

    feast_data = FEATURE_STORE_DIR / "data"
    feast_data.mkdir(parents=True, exist_ok=True)
    feast_path = feast_data / "device_feature_stats.parquet"
    if not stats.empty:
        stats.to_parquet(feast_path, index=False)

    preview = stats.head(5).to_string(index=False) if not stats.empty else "_empty_"
    return MaterializeResult(
        metadata={
            "rows": MetadataValue.int(int(len(stats))),
            "device_types": MetadataValue.int(
                int(stats["device_type"].nunique()) if not stats.empty else 0
            ),
            "artifact_parquet": MetadataValue.path(str(out_parquet)),
            "feast_parquet": MetadataValue.path(str(feast_path)),
            "preview": MetadataValue.text(preview),
        },
    )


@asset(
    key=AssetKey(["drift", "retrain_decision"]),
    group_name="lakehouse_mlops",
    compute_kind="evidently",
    description=(
        "Reads drift-monitor Evidently JSON sidecars and decides whether "
        "retraining should be triggered (replaces sentinel-ray webhook)."
    ),
)
def retrain_decision(context: AssetExecutionContext) -> dict[str, Any]:
    reports_dir = Path(DRIFT_REPORTS_DIR)
    signal = load_latest_drift_signal(reports_dir)
    decision = decide_retraining(
        signal,
        max_score_threshold=RETRAIN_MAX_SCORE_THRESHOLD,
        min_drifted_features=RETRAIN_MIN_DRIFTED_FEATURES,
    )
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS_DIR / "retrain_decision.json"
    out.write_text(json.dumps(decision, indent=2, default=str), encoding="utf-8")
    context.log.info(
        "should_retrain=%s reason=%s max_score=%s",
        decision["should_retrain"],
        decision["reason"],
        decision["max_drift_score"],
    )
    context.add_output_metadata(
        {
            "should_retrain": MetadataValue.bool(bool(decision["should_retrain"])),
            "reason": MetadataValue.text(str(decision["reason"])),
            "max_drift_score": MetadataValue.float(float(decision["max_drift_score"])),
            "drifted_feature_count": MetadataValue.int(
                int(decision["drifted_feature_count"])
            ),
            "artifact": MetadataValue.path(str(out)),
            "reports_dir": MetadataValue.path(str(reports_dir)),
        }
    )
    return decision


@asset(
    key=AssetKey(["qa", "weekly_quarantine_audit"]),
    group_name="lakehouse_mlops",
    compute_kind="pandas",
    description=(
        "Weekly audit of Iceberg fleet.quarantine: top rejection reasons and "
        "worst offending vehicle_ids — nothing silently dropped."
    ),
)
def weekly_quarantine_audit(
    context: AssetExecutionContext,
    iceberg: IcebergTelemetryResource,
) -> dict[str, Any]:
    quarantine = iceberg.load_quarantine()
    report = summarize_quarantine(quarantine)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS_DIR / "weekly_quarantine_audit.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    context.log.info("total_rejected=%s", report["total_rejected"])
    context.add_output_metadata(
        {
            "total_rejected": MetadataValue.int(int(report["total_rejected"])),
            "top_reason": MetadataValue.text(
                report["top_reasons"][0]["key"] if report["top_reasons"] else "n/a"
            ),
            "artifact": MetadataValue.path(str(out)),
            "generated_at": MetadataValue.text(report["generated_at"]),
        }
    )
    return report
