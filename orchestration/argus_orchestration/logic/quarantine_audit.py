"""Summarize fleet.quarantine rejection patterns."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def summarize_quarantine(quarantine: pd.DataFrame, *, top_n: int = 10) -> dict[str, Any]:
    """Build a quarantine audit report dict (artifact-friendly)."""
    if quarantine.empty:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_rejected": 0,
            "top_reasons": [],
            "top_fields": [],
            "top_vehicle_ids": [],
            "by_source_topic": {},
        }

    reason_col = "reason" if "reason" in quarantine.columns else None
    field_col = "field" if "field" in quarantine.columns else None
    vehicle_col = "vehicle_id" if "vehicle_id" in quarantine.columns else None
    topic_col = "source_topic" if "source_topic" in quarantine.columns else None

    def _top(series: pd.Series | None) -> list[dict[str, Any]]:
        if series is None:
            return []
        counts = Counter(str(v) for v in series.dropna().tolist())
        return [
            {"key": key, "count": count}
            for key, count in counts.most_common(top_n)
        ]

    by_topic: dict[str, int] = {}
    if topic_col:
        by_topic = {
            str(k): int(v)
            for k, v in quarantine[topic_col].fillna("unknown").value_counts().items()
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_rejected": int(len(quarantine)),
        "top_reasons": _top(quarantine[reason_col] if reason_col else None),
        "top_fields": _top(quarantine[field_col] if field_col else None),
        "top_vehicle_ids": _top(quarantine[vehicle_col] if vehicle_col else None),
        "by_source_topic": by_topic,
    }
