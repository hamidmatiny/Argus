"""Unit tests for KS-test and embedding-distance drift detection."""

from __future__ import annotations

import numpy as np

from analyzer import (
    DriftAnalyzer,
    compute_drift_report,
    compute_embedding_metrics,
    features_to_embeddings,
    generate_baseline_data,
    ks_feature_test,
    should_raise_incident,
)
from config import DRIFT_FEATURES
from incidents import build_incident_event


def test_ks_detects_shifted_distribution():
    rng = np.random.default_rng(0)
    baseline = rng.normal(0.0, 1.0, 500)
    drifted = rng.normal(3.0, 1.0, 500)
    same = rng.normal(0.0, 1.0, 500)

    drifted_result = ks_feature_test(drifted, baseline, alpha=0.05)
    same_result = ks_feature_test(same, baseline, alpha=0.05)

    assert drifted_result["drift_detected"] is True
    assert drifted_result["p_value"] < 0.05
    assert same_result["drift_detected"] is False


def test_embedding_distance_flags_centroid_shift():
    baseline = generate_baseline_data(300, seed=1)
    drifted = baseline.copy()
    for col in DRIFT_FEATURES:
        drifted[col] = drifted[col] + 10.0

    metrics = compute_embedding_metrics(
        features_to_embeddings(drifted),
        features_to_embeddings(baseline),
    )
    assert metrics["drift_detected"] is True
    assert metrics["mean_euclidean_distance"] > 2.0

    same = compute_embedding_metrics(
        features_to_embeddings(baseline.head(100)),
        features_to_embeddings(baseline),
    )
    assert same["drift_detected"] is False


def test_compute_drift_report_non_drifted_window():
    baseline = generate_baseline_data(400, seed=2)
    window = generate_baseline_data(80, seed=3)
    report = compute_drift_report(window, baseline, alpha=0.001)
    assert report["status"] == "analyzed"
    assert report["window_size"] == 80


def test_compute_drift_report_detects_multi_feature_drift():
    baseline = generate_baseline_data(500, seed=4)
    window = baseline.head(60).copy()
    window["speed_mph"] = window["speed_mph"] + 40.0
    window["lidar_temp_c"] = window["lidar_temp_c"] + 20.0
    window["compute_load_pct"] = window["compute_load_pct"] + 30.0

    report = compute_drift_report(window, baseline, alpha=0.05)
    assert report["drift_detected"] is True
    assert report["drifted_feature_count"] >= 2
    assert should_raise_incident(report, min_features=2) is True


def test_should_raise_incident_threshold():
    report = {
        "drifted_feature_count": 1,
        "drifted_features": ["speed_mph"],
    }
    assert should_raise_incident(report, min_features=2) is False
    report["drifted_feature_count"] = 2
    assert should_raise_incident(report, min_features=2) is True


def test_analyzer_sliding_window_emits_report():
    analyzer = DriftAnalyzer(baseline_samples=50, window_size=20)
    analyzer.seed_synthetic_baseline()
    report = None
    for _ in range(20):
        row = {
            f: float(generate_baseline_data(1, seed=None).iloc[0][f])
            for f in DRIFT_FEATURES
        }
        row["speed_mph"] += 50.0
        row["brake_pressure"] += 1.0
        report = analyzer.ingest(row)
    assert report is not None
    assert report["status"] == "analyzed"


def test_build_incident_event_matches_proto_shape():
    report = {
        "drifted_features": ["speed_mph", "lidar_temp_c"],
        "drifted_feature_count": 2,
        "window_size": 50,
        "alpha": 0.05,
    }
    event = build_incident_event(report, threshold=2)
    assert event["severity"] == "INCIDENT_SEVERITY_CRITICAL"
    assert event["source_service"] == "drift-monitor"
    assert event["metric_name"] == "drifted_feature_count"
    assert event["observed_value"] == 2.0
    assert event["threshold"] == 2.0
    assert event["status"] == "INCIDENT_STATUS_OPEN"
    assert event["incident_id"].startswith("drift-")
