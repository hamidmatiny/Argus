"""Compute per-device_type feature statistics from telemetry rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from argus_orchestration.config import FEATURES


def compute_feature_statistics(
    telemetry: pd.DataFrame,
    *,
    features: tuple[str, ...] = FEATURES,
    computed_at: datetime | None = None,
) -> pd.DataFrame:
    """
    Return one row per device_type with mean/std/p50/p95 per feature.

    Columns: device_type, computed_at, {feature}_mean|_std|_p50|_p95, row_count
    """
    if telemetry.empty:
        return pd.DataFrame()

    frame = telemetry.copy()
    if "device_type" not in frame.columns:
        frame["device_type"] = "DEVICE_TYPE_UNSPECIFIED"

    stamp = computed_at or datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for device_type, group in frame.groupby("device_type", dropna=False):
        row: dict[str, Any] = {
            "device_type": str(device_type),
            "computed_at": stamp,
            "row_count": int(len(group)),
        }
        for feature in features:
            if feature not in group.columns:
                continue
            series = pd.to_numeric(group[feature], errors="coerce").dropna()
            if series.empty:
                row[f"{feature}_mean"] = None
                row[f"{feature}_std"] = None
                row[f"{feature}_p50"] = None
                row[f"{feature}_p95"] = None
                continue
            row[f"{feature}_mean"] = float(series.mean())
            row[f"{feature}_std"] = float(series.std(ddof=0))
            row[f"{feature}_p50"] = float(np.percentile(series, 50))
            row[f"{feature}_p95"] = float(np.percentile(series, 95))
        rows.append(row)
    return pd.DataFrame(rows)
