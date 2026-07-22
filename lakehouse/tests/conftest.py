"""Pytest fixtures: local SqlCatalog warehouse for Iceberg writer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from common.catalog import ensure_table, load_iceberg_catalog
from common.schema import (
    QUARANTINE_PARTITION_SPEC,
    QUARANTINE_SCHEMA,
    TELEMETRY_PARTITION_SPEC,
    TELEMETRY_SCHEMA,
)


@pytest.fixture
def sqlite_catalog(tmp_path: Path):
    warehouse = tmp_path / "warehouse"
    warehouse.mkdir()
    db = tmp_path / "catalog.db"
    catalog = load_iceberg_catalog(
        catalog_type="sqlite",
        warehouse=f"file://{warehouse}",
        sqlite_path=db,
    )
    return catalog


@pytest.fixture
def telemetry_table(sqlite_catalog):
    return ensure_table(
        sqlite_catalog,
        namespace="fleet",
        table_name="telemetry",
        schema=TELEMETRY_SCHEMA,
        partition_spec=TELEMETRY_PARTITION_SPEC,
    )


@pytest.fixture
def quarantine_table(sqlite_catalog):
    return ensure_table(
        sqlite_catalog,
        namespace="fleet",
        table_name="quarantine",
        schema=QUARANTINE_SCHEMA,
        partition_spec=QUARANTINE_PARTITION_SPEC,
    )
