"""Report cadence defaults and retention pruning."""

from __future__ import annotations

import time
from pathlib import Path

from config import EVIDENTLY_EVERY_N_WINDOWS, REPORTS_MAX_FILES
from evidently_report import prune_old_reports, should_run_evidently


def test_evidently_default_is_periodic_not_per_window():
    assert EVIDENTLY_EVERY_N_WINDOWS >= 25
    assert REPORTS_MAX_FILES > 0


def test_should_run_evidently_uses_tumbling_not_every_slide():
    # every_n=2 tumbling windows of size 50 → fire at 100, 200, ...
    assert should_run_evidently(50, every_n=2, window_size=50) is False
    assert should_run_evidently(99, every_n=2, window_size=50) is False
    assert should_run_evidently(100, every_n=2, window_size=50) is True
    assert should_run_evidently(150, every_n=2, window_size=50) is False
    assert should_run_evidently(200, every_n=2, window_size=50) is True


def test_prune_old_reports_keeps_newest_and_latest_signal(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    latest = reports / "latest_drift_signal.json"
    latest.write_text('{"ok": true}', encoding="utf-8")

    stems: list[str] = []
    for i in range(5):
        stem = f"data_drift_20260101T00000{i}Z"
        stems.append(stem)
        (reports / f"{stem}.html").write_text(f"<html>{i}</html>", encoding="utf-8")
        (reports / f"{stem}.json").write_text(f'{{"i": {i}}}', encoding="utf-8")
        time.sleep(0.01)  # ensure distinct mtimes

    removed = prune_old_reports(reports, max_reports=2)
    assert removed == 6  # 3 stems × (html + json)

    remaining_html = sorted(p.name for p in reports.glob("data_drift_*.html"))
    assert remaining_html == [
        "data_drift_20260101T000003Z.html",
        "data_drift_20260101T000004Z.html",
    ]
    assert latest.exists()
    assert latest.read_text(encoding="utf-8") == '{"ok": true}'


def test_prune_disabled_when_max_non_positive(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    for i in range(3):
        (reports / f"data_drift_{i}.html").write_text("x", encoding="utf-8")
    assert prune_old_reports(reports, max_reports=0) == 0
    assert len(list(reports.glob("data_drift_*.html"))) == 3
