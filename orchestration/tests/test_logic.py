"""Unit tests for pure orchestration logic."""

from __future__ import annotations

from argus_orchestration.logic.drift_decision import (
    decide_retraining,
    load_latest_drift_signal,
)
from argus_orchestration.logic.feature_stats import compute_feature_statistics
from argus_orchestration.logic.quarantine_audit import summarize_quarantine


def test_compute_feature_statistics_per_device(sample_telemetry):
    stats = compute_feature_statistics(sample_telemetry)
    assert set(stats["device_type"]) == {
        "DEVICE_TYPE_SIMULATOR",
        "DEVICE_TYPE_VEHICLE",
    }
    assert "speed_mph_mean" in stats.columns
    assert "speed_mph_p95" in stats.columns
    sim = stats.loc[stats["device_type"] == "DEVICE_TYPE_SIMULATOR"].iloc[0]
    veh = stats.loc[stats["device_type"] == "DEVICE_TYPE_VEHICLE"].iloc[0]
    assert veh["speed_mph_mean"] > sim["speed_mph_mean"]


def test_decide_retraining_triggers_on_scores(drift_reports_dir):
    signal = load_latest_drift_signal(drift_reports_dir)
    decision = decide_retraining(
        signal, max_score_threshold=0.5, min_drifted_features=2
    )
    assert decision["should_retrain"] is True
    assert decision["max_drift_score"] == 0.8
    assert decision["drifted_feature_count"] == 2


def test_decide_retraining_below_threshold():
    decision = decide_retraining(
        {
            "feature_scores": {"speed_mph": 0.1},
            "max_drift_score": 0.1,
            "drifted_feature_count": 0,
            "window_size": 50,
        },
        max_score_threshold=0.5,
        min_drifted_features=2,
    )
    assert decision["should_retrain"] is False
    assert decision["reason"] == "below_threshold"


def test_quarantine_audit_tops(sample_quarantine):
    report = summarize_quarantine(sample_quarantine, top_n=5)
    assert report["total_rejected"] == 3
    assert report["top_vehicle_ids"][0]["key"] == "VH-0000001"
    assert report["top_vehicle_ids"][0]["count"] == 2
    assert len(report["top_reasons"]) >= 1
