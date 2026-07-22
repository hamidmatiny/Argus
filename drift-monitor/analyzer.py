"""Kolmogorov-Smirnov + embedding-distance drift analysis (sentinel-ray port)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
from scipy.stats import ks_2samp

from config import (
    DRIFT_ALPHA,
    DRIFT_BASELINE_SAMPLES,
    DRIFT_FEATURES,
    DRIFT_MIN_FEATURES_FOR_INCIDENT,
    DRIFT_WINDOW_SIZE,
    EMBEDDING_COSINE_SIM_THRESHOLD,
    EMBEDDING_EUCLIDEAN_THRESHOLD,
    GOLDEN_BASELINE,
    RANDOM_SEED,
)


def generate_baseline_data(
    num_samples: int | None = None,
    *,
    seed: int | None = None,
) -> pd.DataFrame:
    """Synthetic golden reference matching healthy fleet feature distributions."""
    n = num_samples or DRIFT_BASELINE_SAMPLES
    rng = np.random.default_rng(seed if seed is not None else RANDOM_SEED)
    data: dict[str, Any] = {}
    for feature, (mean, std) in GOLDEN_BASELINE.items():
        data[feature] = rng.normal(mean, std, n).astype(np.float64)
    data["speed_mph"] = np.clip(data["speed_mph"], 0.0, 120.0)
    data["brake_pressure"] = np.clip(data["brake_pressure"], 0.0, None)
    data["compute_load_pct"] = np.clip(data["compute_load_pct"], 0.0, 100.0)
    return pd.DataFrame(data)


def features_to_embeddings(df: pd.DataFrame) -> np.ndarray:
    """
    Treat the monitored feature vector as a tabular embedding.

    Each row → 4-D vector (speed, brake, lidar_temp, compute_load), z-scored
    against GOLDEN_BASELINE so distances are scale-comparable.
    """
    if df.empty:
        return np.empty((0, len(DRIFT_FEATURES)), dtype=np.float64)
    cols = []
    for feature in DRIFT_FEATURES:
        mean, std = GOLDEN_BASELINE[feature]
        std = std if std > 1e-9 else 1.0
        cols.append(((df[feature].astype(np.float64) - mean) / std).to_numpy())
    return np.column_stack(cols)


def compute_embedding_metrics(
    window_embeddings: np.ndarray,
    baseline_embeddings: np.ndarray,
) -> dict[str, float]:
    """Compare window vs baseline embedding centroids (cosine + euclidean)."""
    if window_embeddings.size == 0 or baseline_embeddings.size == 0:
        return {
            "mean_cosine_similarity": 1.0,
            "mean_euclidean_distance": 0.0,
            "drift_detected": False,
        }

    window_centroid = window_embeddings.mean(axis=0, keepdims=True)
    baseline_centroid = baseline_embeddings.mean(axis=0, keepdims=True)

    cosine_distance = float(
        cdist(window_centroid, baseline_centroid, metric="cosine")[0, 0]
    )
    if np.isnan(cosine_distance):
        cosine_distance = 0.0
    cosine_similarity = 1.0 - cosine_distance
    euclidean_distance = float(
        cdist(window_centroid, baseline_centroid, metric="euclidean")[0, 0]
    )

    drifted = (
        cosine_similarity < EMBEDDING_COSINE_SIM_THRESHOLD
        or euclidean_distance > EMBEDDING_EUCLIDEAN_THRESHOLD
    )
    return {
        "mean_cosine_similarity": cosine_similarity,
        "mean_euclidean_distance": euclidean_distance,
        "drift_detected": bool(drifted),
    }


def ks_feature_test(
    window: np.ndarray,
    baseline: np.ndarray,
    *,
    alpha: float = DRIFT_ALPHA,
) -> dict[str, Any]:
    """Two-sample KS test for a single feature."""
    result = ks_2samp(window, baseline)
    return {
        "ks_statistic": float(result.statistic),
        "p_value": float(result.pvalue),
        "drift_detected": bool(result.pvalue < alpha),
        "drift_score": float(result.statistic),  # higher = more drifted
    }


def compute_drift_report(
    window_df: pd.DataFrame,
    baseline_df: pd.DataFrame,
    *,
    alpha: float = DRIFT_ALPHA,
) -> dict[str, Any]:
    """
    Compare a streaming window against the golden baseline.

    Drift per feature: KS p-value < alpha.
    Embedding drift: centroid cosine/euclidean thresholds (sentinel-ray style).
    """
    if window_df.empty:
        return {
            "window_size": 0,
            "status": "skipped",
            "drift_detected": False,
            "features": {},
            "drifted_features": [],
            "reason": "empty_window",
        }

    features: dict[str, Any] = {}
    for feature in DRIFT_FEATURES:
        features[feature] = ks_feature_test(
            window_df[feature].to_numpy(dtype=np.float64),
            baseline_df[feature].to_numpy(dtype=np.float64),
            alpha=alpha,
        )

    embedding_metrics = compute_embedding_metrics(
        features_to_embeddings(window_df),
        features_to_embeddings(baseline_df),
    )
    # Also KS on embedding L2 norms (sentinel-ray).
    window_norms = np.linalg.norm(features_to_embeddings(window_df), axis=1)
    baseline_norms = np.linalg.norm(features_to_embeddings(baseline_df), axis=1)
    embedding_ks = ks_feature_test(window_norms, baseline_norms, alpha=alpha)
    features["embedding"] = {
        **embedding_ks,
        **embedding_metrics,
        "drift_detected": bool(
            embedding_ks["drift_detected"] or embedding_metrics["drift_detected"]
        ),
        "drift_score": float(
            max(
                embedding_ks["drift_score"],
                embedding_metrics["mean_euclidean_distance"]
                / max(EMBEDDING_EUCLIDEAN_THRESHOLD, 1e-9),
            )
        ),
    }

    drifted = [name for name, meta in features.items() if meta.get("drift_detected")]
    return {
        "window_size": len(window_df),
        "status": "analyzed",
        "drift_detected": len(drifted) > 0,
        "alpha": alpha,
        "features": features,
        "drifted_features": drifted,
        "drifted_feature_count": len(drifted),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


def should_raise_incident(
    report: dict[str, Any],
    *,
    min_features: int = DRIFT_MIN_FEATURES_FOR_INCIDENT,
) -> bool:
    """True when >= N features drifted (sentinel-ray DRIFT_MIN_FEATURES_FOR_INCIDENT)."""
    return int(report.get("drifted_feature_count", 0)) >= min_features


@dataclass
class DriftAnalyzer:
    """
    Stateful analyzer: build baseline from a reference window, then sliding KS.

    Unlike sentinel-ray's Ray actor, this reads batches fed from Kafka.
    """

    baseline_samples: int = DRIFT_BASELINE_SAMPLES
    window_size: int = DRIFT_WINDOW_SIZE
    alpha: float = DRIFT_ALPHA
    min_features_for_incident: int = DRIFT_MIN_FEATURES_FOR_INCIDENT
    _baseline_df: pd.DataFrame | None = field(default=None, init=False, repr=False)
    _baseline_built_at: datetime | None = field(default=None, init=False, repr=False)
    _buffer: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _reference_buffer: list[dict[str, Any]] = field(
        default_factory=list, init=False, repr=False
    )
    records_evaluated: int = field(default=0, init=False)

    @property
    def baseline_ready(self) -> bool:
        return self._baseline_df is not None and len(self._baseline_df) > 0

    @property
    def baseline_staleness_seconds(self) -> float:
        if self._baseline_built_at is None:
            return 0.0
        return (datetime.now(timezone.utc) - self._baseline_built_at).total_seconds()

    def seed_synthetic_baseline(self) -> None:
        """Optional bootstrap when Kafka has no validated history yet."""
        self._baseline_df = generate_baseline_data(self.baseline_samples)
        self._baseline_built_at = datetime.now(timezone.utc)

    def ingest(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """
        Ingest one validated telemetry record.

        Returns a drift report when a sliding window is ready; otherwise None.
        During startup, accumulates a reference window as the golden baseline.
        """
        row = {f: float(record[f]) for f in DRIFT_FEATURES if f in record}
        if len(row) < len(DRIFT_FEATURES):
            return None

        self.records_evaluated += 1

        if not self.baseline_ready:
            self._reference_buffer.append(row)
            if len(self._reference_buffer) >= self.baseline_samples:
                self._baseline_df = pd.DataFrame(self._reference_buffer)
                self._baseline_built_at = datetime.now(timezone.utc)
                self._reference_buffer.clear()
            return None

        self._buffer.append(row)
        if len(self._buffer) < self.window_size:
            return None

        window_df = pd.DataFrame(self._buffer[-self.window_size :])
        # Sliding: drop oldest to keep buffer bounded.
        overflow = len(self._buffer) - self.window_size
        if overflow > 0:
            self._buffer = self._buffer[overflow:]

        assert self._baseline_df is not None
        return compute_drift_report(window_df, self._baseline_df, alpha=self.alpha)

    def feature_drift_scores(self, report: dict[str, Any] | None) -> dict[str, float]:
        if not report or report.get("status") != "analyzed":
            return {f: 0.0 for f in (*DRIFT_FEATURES, "embedding")}
        return {
            name: float(meta.get("drift_score", 0.0))
            for name, meta in report.get("features", {}).items()
        }
