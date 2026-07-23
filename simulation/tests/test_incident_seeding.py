"""Unit tests for drift-signature → scenario_runner parameter mapping."""

from __future__ import annotations

from argus_pipeline.incident_seeding import scenario_params_from_drift_decision


def test_scenario_params_picks_hard_brake_when_brake_dominates():
    params = scenario_params_from_drift_decision(
        {
            "feature_scores": {"brake_pressure": 0.9, "speed_mph": 0.2},
            "reason": "max_drift_score",
            "max_drift_score": 0.9,
        },
        n_frames=12,
    )
    assert params["scenario_type"] == "hard_brake"
    assert params["n_frames"] == 12
    assert params["drift_signature"]["brake_pressure"] == 0.9
    assert params["drift_signature"]["speed_mph"] == 0.2
    assert params["source_reason"] == "max_drift_score"
    assert params["max_drift_score"] == 0.9


def test_scenario_params_picks_highway_merge_when_speed_dominates():
    params = scenario_params_from_drift_decision(
        {
            "feature_scores": {"brake_pressure": 0.1, "speed_mph": 0.85},
            "reason": "score_and_feature_count",
            "max_drift_score": 0.85,
        }
    )
    assert params["scenario_type"] == "highway_merge"
    assert params["drift_signature"]["speed_mph"] == 0.85
    assert params["drift_signature"]["brake_pressure"] == 0.1


def test_scenario_params_picks_intersection_when_neither_present():
    params = scenario_params_from_drift_decision(
        {
            "feature_scores": {"lidar_temp_c": 0.7},
            "reason": "drifted_feature_count",
            "max_drift_score": 0.7,
        }
    )
    assert params["scenario_type"] == "intersection"
    assert params["drift_signature"]["brake_pressure"] == 0.0
    assert params["drift_signature"]["speed_mph"] == 0.0
    assert params["drift_signature"]["lidar_temp_c"] == 0.7


def test_scenario_params_intersection_on_empty_scores():
    params = scenario_params_from_drift_decision({"feature_scores": {}})
    assert params["scenario_type"] == "intersection"
