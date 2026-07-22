"""Rolling quarantine-rate metrics (sentinel-ray ORCHESTRATOR_QA_WINDOW pattern)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque


# Mirror sentinel-ray defaults.
QA_WINDOW_EVENTS = 20  # tumbling window size per vehicle (event count)
QA_QUARANTINE_RATE_THRESHOLD = 0.15


@dataclass
class WindowStats:
    total: int = 0
    quarantined: int = 0

    @property
    def quarantine_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.quarantined / self.total


def compute_quarantine_rate(total: int, quarantined: int) -> float:
    if total <= 0:
        return 0.0
    return quarantined / total


def rate_exceeds_threshold(
    rate: float, threshold: float = QA_QUARANTINE_RATE_THRESHOLD
) -> bool:
    return rate > threshold


@dataclass
class QaMetricEvent:
    vehicle_id: str
    window_size: int
    total: int
    quarantined: int
    quarantine_rate: float
    threshold: float
    exceeded: bool
    window_end: str

    def to_dict(self) -> dict:
        return {
            "vehicle_id": self.vehicle_id,
            "window_size": self.window_size,
            "total": self.total,
            "quarantined": self.quarantined,
            "quarantine_rate": round(self.quarantine_rate, 6),
            "threshold": self.threshold,
            "exceeded": self.exceeded,
            "window_end": self.window_end,
            "type": "qa_quarantine_rate",
        }


class TumblingQuarantineWindow:
    """
    Per-vehicle tumbling count window.

    Each closed window emits a QaMetricEvent (mirrors sentinel-ray rolling
    quarantine rate over ORCHESTRATOR_QA_WINDOW_BATCHES).
    """

    def __init__(
        self,
        window_size: int = QA_WINDOW_EVENTS,
        threshold: float = QA_QUARANTINE_RATE_THRESHOLD,
    ) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self.window_size = window_size
        self.threshold = threshold
        self._buffers: dict[str, Deque[bool]] = defaultdict(deque)

    def observe(self, vehicle_id: str, quarantined: bool) -> QaMetricEvent | None:
        """Record one validation outcome; return metric when the window closes."""
        buf = self._buffers[vehicle_id]
        buf.append(bool(quarantined))
        if len(buf) < self.window_size:
            return None
        # Close tumbling window.
        outcomes = list(buf)
        buf.clear()
        total = len(outcomes)
        q = sum(1 for x in outcomes if x)
        rate = compute_quarantine_rate(total, q)
        return QaMetricEvent(
            vehicle_id=vehicle_id,
            window_size=self.window_size,
            total=total,
            quarantined=q,
            quarantine_rate=rate,
            threshold=self.threshold,
            exceeded=rate_exceeds_threshold(rate, self.threshold),
            window_end=datetime.now(timezone.utc).isoformat(),
        )
