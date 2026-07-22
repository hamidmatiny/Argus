"""Drift-monitor configuration (sentinel-ray thresholds, fleet features)."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = Path(os.getenv("DRIFT_REPORTS_DIR", str(PROJECT_ROOT / "reports")))

# Features monitored for distribution drift (validated telemetry).
DRIFT_FEATURES: tuple[str, ...] = (
    "speed_mph",
    "brake_pressure",
    "lidar_temp_c",
    "compute_load_pct",
)

# Rough mean/std for synthetic cold-start + embedding z-scores ONLY.
# Empirically measured from ingestion/simulator kinematics (n≈5000, 20 vehicles,
# 1s ticks, failure_rate=0) — NOT a substitute for a live baseline from
# telemetry.validated. Live accumulation always replaces this when available.
GOLDEN_BASELINE: dict[str, tuple[float, float]] = {
    "speed_mph": (22.0, 19.7),
    "brake_pressure": (0.27, 0.20),
    "lidar_temp_c": (39.8, 1.8),
    "compute_load_pct": (40.7, 12.4),
}

DRIFT_BASELINE_SAMPLES = int(os.getenv("DRIFT_BASELINE_SAMPLES", "200"))
# Discard this many validated records before freezing the live baseline so a
# joint simulator+monitor restart doesn't capture cold-start kinematics.
DRIFT_BASELINE_WARMUP_SAMPLES = int(os.getenv("DRIFT_BASELINE_WARMUP_SAMPLES", "200"))
DRIFT_WINDOW_SIZE = int(os.getenv("DRIFT_WINDOW_SIZE", "50"))
DRIFT_ALPHA = float(os.getenv("DRIFT_ALPHA", "0.05"))
DRIFT_MIN_FEATURES_FOR_INCIDENT = int(os.getenv("DRIFT_MIN_FEATURES_FOR_INCIDENT", "2"))

# Embedding-distance thresholds on the feature-vector centroid (4-D embedding).
EMBEDDING_COSINE_SIM_THRESHOLD = float(os.getenv("EMBEDDING_COSINE_SIM_THRESHOLD", "0.85"))
EMBEDDING_EUCLIDEAN_THRESHOLD = float(os.getenv("EMBEDDING_EUCLIDEAN_THRESHOLD", "2.0"))

RANDOM_SEED = int(os.getenv("DRIFT_RANDOM_SEED", "42"))

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:19092")
SOURCE_TOPIC = os.getenv("DRIFT_SOURCE_TOPIC", "telemetry.validated")
INCIDENTS_TOPIC = os.getenv("DRIFT_INCIDENTS_TOPIC", "incidents.raw")
GROUP_ID = os.getenv("DRIFT_KAFKA_GROUP_ID", "argus-drift-monitor")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:18081")

HEALTH_PORT = int(os.getenv("DRIFT_HEALTH_PORT", "8094"))
METRICS_PORT = int(os.getenv("DRIFT_METRICS_PORT", "8095"))

# How often (records) to run Evidently + persist HTML under reports/.
EVIDENTLY_EVERY_N_WINDOWS = int(os.getenv("DRIFT_EVIDENTLY_EVERY_N_WINDOWS", "1"))
