"""Dagster asset materialization tests against fixture data."""

from __future__ import annotations

import json

from dagster import materialize

from argus_orchestration.assets import (
    daily_feature_statistics,
    retrain_decision,
    weekly_quarantine_audit,
)
from argus_orchestration.resources import IcebergTelemetryResource


def test_materialize_daily_feature_statistics(tmp_path, sample_telemetry, monkeypatch):
    telem_path = tmp_path / "telemetry.parquet"
    sample_telemetry.to_parquet(telem_path, index=False)
    artifacts = tmp_path / "artifacts"
    feast = tmp_path / "feature_store"
    monkeypatch.setenv("ORCH_ARTIFACTS_DIR", str(artifacts))
    monkeypatch.setenv("FEAST_REPO_PATH", str(feast))

    # Reload config paths picked up at import — patch module globals.
    import argus_orchestration.assets as assets_mod
    import argus_orchestration.config as cfg

    monkeypatch.setattr(cfg, "ARTIFACTS_DIR", artifacts)
    monkeypatch.setattr(cfg, "FEATURE_STORE_DIR", feast)
    monkeypatch.setattr(assets_mod, "ARTIFACTS_DIR", artifacts)
    monkeypatch.setattr(assets_mod, "FEATURE_STORE_DIR", feast)

    result = materialize(
        [daily_feature_statistics],
        resources={
            "iceberg": IcebergTelemetryResource(
                fixture_telemetry_path=str(telem_path)
            )
        },
    )
    assert result.success
    assert (artifacts / "daily_feature_statistics.parquet").is_file()
    assert (feast / "data" / "device_feature_stats.parquet").is_file()


def test_materialize_retrain_decision(tmp_path, drift_reports_dir, monkeypatch):
    artifacts = tmp_path / "artifacts"
    import argus_orchestration.assets as assets_mod
    import argus_orchestration.config as cfg

    monkeypatch.setattr(cfg, "ARTIFACTS_DIR", artifacts)
    monkeypatch.setattr(cfg, "DRIFT_REPORTS_DIR", drift_reports_dir)
    monkeypatch.setattr(assets_mod, "ARTIFACTS_DIR", artifacts)
    monkeypatch.setattr(assets_mod, "DRIFT_REPORTS_DIR", drift_reports_dir)

    result = materialize([retrain_decision])
    assert result.success
    decision_path = artifacts / "retrain_decision.json"
    assert decision_path.is_file()
    decision = json.loads(decision_path.read_text())
    assert decision["should_retrain"] is True


def test_materialize_quarantine_audit(tmp_path, sample_quarantine, monkeypatch):
    q_path = tmp_path / "quarantine.parquet"
    sample_quarantine.to_parquet(q_path, index=False)
    artifacts = tmp_path / "artifacts"
    import argus_orchestration.assets as assets_mod
    import argus_orchestration.config as cfg

    monkeypatch.setattr(cfg, "ARTIFACTS_DIR", artifacts)
    monkeypatch.setattr(assets_mod, "ARTIFACTS_DIR", artifacts)

    result = materialize(
        [weekly_quarantine_audit],
        resources={
            "iceberg": IcebergTelemetryResource(fixture_quarantine_path=str(q_path))
        },
    )
    assert result.success
    report = json.loads((artifacts / "weekly_quarantine_audit.json").read_text())
    assert report["total_rejected"] == 3


def test_trigger_retraining_op_skips_when_not_needed():
    """Op returns triggered=False when decision says no — no Kafka/MLflow side effects."""
    from dagster import build_op_context

    from argus_orchestration.ops import trigger_retraining
    from argus_orchestration.resources import KafkaPublisherResource, MLflowResource

    class _NoopMLflow(MLflowResource):
        def log_retraining_run(self, *, params, metrics):  # noqa: ANN001
            raise AssertionError("should not log when should_retrain is false")

    class _NoopKafka(KafkaPublisherResource):
        def publish(self, event):  # noqa: ANN001
            raise AssertionError("should not publish")

    out = trigger_retraining(
        build_op_context(),
        {
            "should_retrain": False,
            "reason": "below_threshold",
            "max_drift_score": 0.1,
            "drifted_feature_count": 0,
            "feature_scores": {},
            "window_size": 50,
        },
        {"seeded": False, "reason": "no_retrain"},
        _NoopMLflow(),
        _NoopKafka(),
    )
    assert out["triggered"] is False
    assert out["synthetic_seed"]["seeded"] is False


def test_seed_synthetic_invokes_run_pipeline_when_enabled(tmp_path, monkeypatch):
    """Enabled path must call run_pipeline (mocked) — not only the skip branches."""
    from dagster import build_op_context

    import argus_orchestration.ops as ops_mod
    import argus_pipeline.runner as runner_mod

    monkeypatch.setattr(ops_mod, "SEED_SYNTHETIC_FROM_DRIFT", True)
    monkeypatch.setattr(ops_mod, "SYNTHETIC_SCENARIO_FRAMES", 8)
    monkeypatch.setenv("ORCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    calls: list[dict] = []

    def _fake_run_pipeline(config):  # noqa: ANN001
        calls.append(dict(config))
        return {
            "batch_sizes": {"scenario_runner": 8, "physics": 8},
            "sinks": {
                "scenario_ground_truth": {"rows": 8, "table": "fleet.scenario_ground_truth"},
                "synthetic_sensor_data": {"rows": 8, "table": "fleet.synthetic_sensor_data"},
            },
        }

    # Op imports run_pipeline inside the function body — patch the module attribute.
    monkeypatch.setattr(runner_mod, "run_pipeline", _fake_run_pipeline)

    decision = {
        "should_retrain": True,
        "reason": "max_drift_score",
        "max_drift_score": 0.9,
        "drifted_feature_count": 2,
        "feature_scores": {"brake_pressure": 0.9, "speed_mph": 0.2},
        "window_size": 100,
        "source_report": None,
    }
    out = ops_mod.seed_synthetic_scenarios_from_incident(build_op_context(), decision)

    assert out["seeded"] is True
    assert out["scenario_type"] == "hard_brake"
    assert out["drift_signature"]["brake_pressure"] == 0.9
    assert len(calls) == 1
    assert calls[0]["scenario_type"] == "hard_brake"
    assert calls[0]["n_frames"] == 8
    assert calls[0]["catalog_type"] == "sqlite"
    assert "sim_warehouse" in calls[0]["warehouse"]
    assert out["batch_sizes"]["scenario_runner"] == 8
    assert out["sinks"]["synthetic_sensor_data"]["rows"] == 8
