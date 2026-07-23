"""Map drift-monitor / retrain decision signatures → scenario_runner config."""

from __future__ import annotations

from typing import Any, Mapping

from argus_pipeline.sources.scenario_runner import SCENARIO_TYPES


def scenario_params_from_drift_decision(
    decision: Mapping[str, Any],
    *,
    n_frames: int = 24,
) -> dict[str, Any]:
    """
    Derive scenario_runner parameters from a drift / retrain decision.

    Uses feature_scores (e.g. brake_pressure, speed_mph) to pick a scenario type
    that stresses the drifted dimensions — for targeted synthetic training data.
    """
    scores = {
        str(k): float(v) for k, v in (decision.get("feature_scores") or {}).items()
    }
    brake = scores.get("brake_pressure", 0.0)
    speed = scores.get("speed_mph", 0.0)

    if brake >= speed and brake > 0.0:
        scenario_type = "hard_brake"
    elif speed > 0.0:
        scenario_type = "highway_merge"
    else:
        scenario_type = "intersection"

    if scenario_type not in SCENARIO_TYPES:
        scenario_type = "hard_brake"

    return {
        "scenario_type": scenario_type,
        "n_frames": n_frames,
        "seed": int(1000 * (brake + speed)) % 10_000,
        "drift_signature": {
            "brake_pressure": brake,
            "speed_mph": speed,
            **{k: v for k, v in scores.items() if k not in {"brake_pressure", "speed_mph"}},
        },
        "source_reason": decision.get("reason"),
        "max_drift_score": decision.get("max_drift_score"),
    }
