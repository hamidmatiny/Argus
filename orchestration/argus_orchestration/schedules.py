"""Schedules for daily feature stats and weekly quarantine audit."""

from __future__ import annotations

from dagster import AssetSelection, ScheduleDefinition, define_asset_job

daily_feature_stats_job = define_asset_job(
    name="daily_feature_stats_job",
    selection=AssetSelection.keys(["lakehouse", "daily_feature_statistics"]),
    description="Materialize daily Iceberg feature statistics",
)

weekly_quarantine_audit_job = define_asset_job(
    name="weekly_quarantine_audit_job",
    selection=AssetSelection.keys(["qa", "weekly_quarantine_audit"]),
    description="Materialize weekly quarantine audit report",
)

drift_decision_job = define_asset_job(
    name="drift_decision_job",
    selection=AssetSelection.keys(["drift", "retrain_decision"]),
    description="Materialize retrain decision from Evidently sidecars",
)

daily_feature_stats_schedule = ScheduleDefinition(
    job=daily_feature_stats_job,
    cron_schedule="0 6 * * *",
    name="daily_feature_stats_schedule",
)

weekly_quarantine_audit_schedule = ScheduleDefinition(
    job=weekly_quarantine_audit_job,
    cron_schedule="0 7 * * 1",
    name="weekly_quarantine_audit_schedule",
)

# Evaluate drift → decision hourly; pair with drift_retrain_job in UI/daemon.
hourly_drift_decision_schedule = ScheduleDefinition(
    job=drift_decision_job,
    cron_schedule="0 * * * *",
    name="hourly_drift_decision_schedule",
)
