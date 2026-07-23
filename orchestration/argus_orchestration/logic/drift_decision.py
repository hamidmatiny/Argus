"""Decide whether to trigger retraining from Evidently JSON sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_latest_drift_signal(reports_dir: Path) -> dict[str, Any] | None:
    """Load latest_drift_signal.json or the newest data_drift_*.json sidecar."""
    latest = reports_dir / "latest_drift_signal.json"
    if latest.is_file():
        return json.loads(latest.read_text(encoding="utf-8"))

    candidates = sorted(
        reports_dir.glob("data_drift_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def decide_retraining(
    signal: dict[str, Any] | None,
    *,
    max_score_threshold: float,
    min_drifted_features: int,
) -> dict[str, Any]:
    """
    Return a structured retrain decision.

    Triggers when max feature drift score >= threshold OR drifted feature
    count >= min_drifted_features (aligned with drift-monitor incident gate).
    """
    if not signal:
        return {
            "should_retrain": False,
            "reason": "no_evidently_signal",
            "max_drift_score": 0.0,
            "drifted_feature_count": 0,
            "feature_scores": {},
            "window_size": 0,
            "source_report": None,
        }

    scores = {str(k): float(v) for k, v in (signal.get("feature_scores") or {}).items()}
    max_score = float(
        signal.get("max_drift_score")
        if signal.get("max_drift_score") is not None
        else (max(scores.values()) if scores else 0.0)
    )
    drifted_count = int(
        signal.get("drifted_feature_count")
        if signal.get("drifted_feature_count") is not None
        else sum(1 for v in scores.values() if v > 0.0)
    )

    by_score = max_score >= max_score_threshold
    by_count = drifted_count >= min_drifted_features
    should = by_score or by_count
    if should and by_score and by_count:
        reason = "score_and_feature_count"
    elif should and by_score:
        reason = "max_drift_score"
    elif should:
        reason = "drifted_feature_count"
    else:
        reason = "below_threshold"

    return {
        "should_retrain": should,
        "reason": reason,
        "max_drift_score": max_score,
        "drifted_feature_count": drifted_count,
        "feature_scores": scores,
        "window_size": int(signal.get("window_size") or 0),
        "source_report": signal.get("html_report"),
        "generated_at": signal.get("generated_at"),
    }
