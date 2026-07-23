"""Shared fixtures for simulation pipeline tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def pipeline_config(tmp_path: Path) -> dict:
    warehouse = tmp_path / "warehouse"
    warehouse.mkdir()
    return {
        "scenario_type": "hard_brake",
        "n_frames": 8,
        "seed": 11,
        "base_timestamp": "2026-07-22T12:00:00+00:00",
        "catalog_type": "sqlite",
        "warehouse": f"file://{warehouse}",
        "sqlite_path": str(tmp_path / "catalog.db"),
        "dry_run": False,
    }
