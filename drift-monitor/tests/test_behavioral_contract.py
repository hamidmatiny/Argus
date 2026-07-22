"""Behavioral contract: low FP on same-distribution traffic; detect real shifts."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ingestion.simulator.generator import (  # noqa: E402
    VehicleTelemetrySimulator,
    default_vehicle_ids,
)

from analyzer import DriftAnalyzer, should_raise_incident  # noqa: E402
from config import DRIFT_FEATURES  # noqa: E402


def _warm_and_sample(
    sim: VehicleTelemetrySimulator,
    n: int,
    *,
    dt: float = 1.0,
    speed_shift: float = 0.0,
) -> list[dict[str, float]]:
    """Advance kinematics with fixed dt and return drift-monitor feature rows."""
    rows: list[dict[str, float]] = []
    for i in range(n):
        vid = sim.vehicle_ids[i % len(sim.vehicle_ids)]
        sim._states[vid].last_updated = time.time() - dt
        payload = sim.generate_ping(vid)
        row = {f: float(payload[f]) for f in DRIFT_FEATURES}
        if speed_shift:
            row["speed_mph"] = row["speed_mph"] + speed_shift
            # Keep dependent-ish features consistent with a world shift.
            row["brake_pressure"] = min(1.0, row["brake_pressure"] + speed_shift / 100.0)
            row["lidar_temp_c"] = row["lidar_temp_c"] + speed_shift * 0.08
            row["compute_load_pct"] = min(100.0, row["compute_load_pct"] + speed_shift * 0.6)
        rows.append(row)
    return rows


@pytest.fixture
def warmed_sim() -> VehicleTelemetrySimulator:
    # Fleet size matters: tiny fleets make the aggregate speed distribution
    # non-stationary (few random walks), which is not "no-shift" traffic.
    sim = VehicleTelemetrySimulator(
        default_vehicle_ids(12), failure_rate=0.0, seed=42
    )
    # Reach steady-ish kinematics before any baseline / eval windows.
    _warm_and_sample(sim, 400)
    return sim


def test_same_simulator_distribution_keeps_incident_rate_low(warmed_sim):
    """
    Live baseline + subsequent windows from the SAME generator → incidents rare.

    Catches the reference-data bug where a mismatched synthetic Gaussian baseline
    made nearly every window look drifted.
    """
    analyzer = DriftAnalyzer(
        baseline_samples=200,
        warmup_samples=0,  # fixture already warmed the simulator
        window_size=50,
        alpha=0.05,
        min_features_for_incident=2,
    )
    for row in _warm_and_sample(warmed_sim, 200):
        assert analyzer.ingest(row) is None
    assert analyzer.baseline_ready is True
    assert analyzer.baseline_source == "live"

    windows = 0
    incidents = 0
    # 50 sliding evaluation windows (first needs 50 samples; then +1 each).
    for row in _warm_and_sample(warmed_sim, 50 + 49):
        report = analyzer.ingest(row)
        if report is None:
            continue
        windows += 1
        if should_raise_incident(report, min_features=2):
            incidents += 1

    assert windows == 50, f"expected 50 eval windows, got {windows}"
    rate = incidents / windows
    assert rate < 0.10, (
        f"incident rate {rate:.0%} ({incidents}/{windows}) under no-shift "
        f"simulator traffic; expected < 10% (alpha false-positive budget)"
    )


def test_shifted_speed_distribution_is_detected(warmed_sim):
    """Deliberate multi-std speed shift must raise an incident."""
    analyzer = DriftAnalyzer(
        baseline_samples=200,
        warmup_samples=0,
        window_size=50,
        alpha=0.05,
        min_features_for_incident=2,
    )
    for row in _warm_and_sample(warmed_sim, 200):
        analyzer.ingest(row)
    assert analyzer.baseline_ready

    # ~3+ stds on speed (~20 mph) plus coupled feature shifts.
    report = None
    for row in _warm_and_sample(warmed_sim, 50, speed_shift=45.0):
        report = analyzer.ingest(row)
    assert report is not None
    assert report["drift_detected"] is True
    assert should_raise_incident(report, min_features=2) is True
    assert "speed_mph" in report["drifted_features"]
