"""Shared helpers to open lakehouse Iceberg tables from simulation sinks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

# Allow ``from common.catalog import …`` the same way lakehouse tests do.
_LAKEHOUSE_ROOT = Path(__file__).resolve().parents[3] / "lakehouse"
if str(_LAKEHOUSE_ROOT) not in sys.path:
    sys.path.insert(0, str(_LAKEHOUSE_ROOT))


def open_catalog(config: Mapping[str, Any]):
    from common.catalog import load_iceberg_catalog

    return load_iceberg_catalog(
        catalog_type=str(config.get("catalog_type") or "sqlite"),
        warehouse=str(config.get("warehouse") or "file:///tmp/argus-sim-warehouse"),
        sqlite_path=config.get("sqlite_path"),
        uri=config.get("catalog_uri"),
    )


def append_rows(table, rows: list[dict[str, Any]], to_arrow) -> int:
    from common.sink import IcebergBatchSink

    if not rows:
        return 0
    sink = IcebergBatchSink(
        table,
        to_arrow=to_arrow,
        batch_size=max(len(rows), 1),
        flush_interval_sec=3600.0,
    )
    for row in rows:
        sink.add(row)
    sink.flush()
    return sink.rows_appended


def json_dumps(value: Any) -> str:
    return json.dumps(value, default=str)
