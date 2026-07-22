"""Buffered Iceberg append sink (Snappy Parquet under Iceberg commits)."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from pyiceberg.table import Table

logger = logging.getLogger("argus.lakehouse.sink")


class IcebergBatchSink:
    """Accumulate mapped rows and append as Iceberg transactions."""

    def __init__(
        self,
        table: Table,
        *,
        to_arrow: Callable[[list[dict[str, Any]]], Any],
        batch_size: int,
        flush_interval_sec: float,
    ) -> None:
        self.table = table
        self._to_arrow = to_arrow
        self.batch_size = max(1, batch_size)
        self.flush_interval_sec = max(0.1, flush_interval_sec)
        self._buffer: list[dict[str, Any]] = []
        self._last_flush = time.monotonic()
        self.rows_appended = 0
        self.flushes = 0

    def add(self, row: dict[str, Any]) -> None:
        self._buffer.append(row)
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def maybe_flush(self) -> None:
        if not self._buffer:
            return
        if time.monotonic() - self._last_flush >= self.flush_interval_sec:
            self.flush()

    def flush(self) -> int:
        if not self._buffer:
            return 0
        batch = self._buffer
        self._buffer = []
        arrow = self._to_arrow(batch)
        self.table.append(arrow)
        n = len(batch)
        self.rows_appended += n
        self.flushes += 1
        self._last_flush = time.monotonic()
        logger.info(
            "iceberg_append",
            extra={
                "rows": n,
                "flushes": self.flushes,
                "rows_appended": self.rows_appended,
                "table": str(self.table.name()),
            },
        )
        return n
