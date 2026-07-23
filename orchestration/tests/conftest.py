"""Shared fixtures for orchestration tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def sample_telemetry() -> pd.DataFrame:
    rows = []
    for device in ("DEVICE_TYPE_SIMULATOR", "DEVICE_TYPE_VEHICLE"):
        for i in range(30):
            rows.append(
                {
                    "vehicle_id": f"VH-{i:07d}",
                    "device_type": device,
                    "speed_mph": 20.0 + i + (5 if device.endswith("VEHICLE") else 0),
                    "brake_pressure": 0.2 + i * 0.01,
                    "lidar_temp_c": 40.0 + i * 0.1,
                    "compute_load_pct": 35.0 + i,
                    "timestamp": datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def sample_quarantine() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rejected_at": datetime(2026, 7, 22, tzinfo=timezone.utc),
                "source_topic": "telemetry.normalized",
                "vehicle_id": "VH-0000001",
                "field": "gps_lat",
                "rule": "range",
                "reason": "latitude out of bounds",
            },
            {
                "rejected_at": datetime(2026, 7, 22, tzinfo=timezone.utc),
                "source_topic": "telemetry.normalized",
                "vehicle_id": "VH-0000001",
                "field": "speed_mph",
                "rule": "range",
                "reason": "speed too high",
            },
            {
                "rejected_at": datetime(2026, 7, 22, tzinfo=timezone.utc),
                "source_topic": "telemetry.raw",
                "vehicle_id": "VH-0000009",
                "field": "vehicle_id",
                "rule": "pattern",
                "reason": "bad id",
            },
        ]
    )


@pytest.fixture
def drift_reports_dir(tmp_path: Path) -> Path:
    reports = tmp_path / "reports"
    reports.mkdir()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "html_report": "data_drift_test.html",
        "window_size": 50,
        "feature_scores": {
            "speed_mph": 0.8,
            "brake_pressure": 0.7,
            "lidar_temp_c": 0.1,
            "compute_load_pct": 0.2,
        },
        "drifted_feature_count": 2,
        "max_drift_score": 0.8,
    }
    (reports / "latest_drift_signal.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    (reports / "data_drift_test.html").write_text("<html></html>", encoding="utf-8")
    return reports
