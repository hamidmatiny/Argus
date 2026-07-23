"""CLI: consume telemetry.quarantine → Iceberg fleet.quarantine (audit archive)."""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_REPO = _ROOT.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from kafka import KafkaConsumer  # noqa: E402

from common.catalog import ensure_table, load_iceberg_catalog  # noqa: E402
from common.config import (  # noqa: E402
    BATCH_SIZE,
    DLQ_GROUP_ID,
    DLQ_HEALTH_PORT,
    FLUSH_INTERVAL_SEC,
    KAFKA_BROKERS,
    NAMESPACE,
    QUARANTINE_TABLE,
    QUARANTINE_TOPIC,
)
from common.health import start_health_server  # noqa: E402
from common.logging_util import setup_logging  # noqa: E402
from common.schema import (  # noqa: E402
    QUARANTINE_PARTITION_SPEC,
    QUARANTINE_SCHEMA,
    map_quarantine_record,
    quarantine_rows_to_arrow,
)
from common.sink import IcebergBatchSink  # noqa: E402

_shutdown = threading.Event()
_stats: dict[str, Any] = {
    "records_consumed": 0,
    "rows_appended": 0,
    "flushes": 0,
    "decode_errors": 0,
    "map_errors": 0,
}
_ready = False


def _handle_signal(signum: int, _frame: object) -> None:
    _shutdown.set()


def decode_value(value: bytes) -> dict | None:
    try:
        obj = json.loads(value.decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def run() -> int:
    global _ready
    logger = setup_logging("argus.lakehouse.dlq_writer", os.getenv("LOG_LEVEL", "INFO"))
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    start_health_server(
        DLQ_HEALTH_PORT,
        stats_provider=lambda: dict(_stats),
        ready_provider=lambda: _ready,
        writer_name="dlq",
    )

    catalog = load_iceberg_catalog()
    table = ensure_table(
        catalog,
        namespace=NAMESPACE,
        table_name=QUARANTINE_TABLE,
        schema=QUARANTINE_SCHEMA,
        partition_spec=QUARANTINE_PARTITION_SPEC,
    )
    sink = IcebergBatchSink(
        table,
        to_arrow=quarantine_rows_to_arrow,
        batch_size=BATCH_SIZE,
        flush_interval_sec=FLUSH_INTERVAL_SEC,
    )

    consumer = KafkaConsumer(
        QUARANTINE_TOPIC,
        bootstrap_servers=[b.strip() for b in KAFKA_BROKERS.split(",") if b.strip()],
        group_id=DLQ_GROUP_ID,
        client_id="argus-lakehouse-dlq-writer",
        enable_auto_commit=True,
        auto_offset_reset="earliest",
        consumer_timeout_ms=1000,
    )
    _ready = True
    logger.info(
        "lakehouse_dlq_writer_started",
        extra={
            "topic": QUARANTINE_TOPIC,
            "table": f"{NAMESPACE}.{QUARANTINE_TABLE}",
            "health_port": DLQ_HEALTH_PORT,
        },
    )

    try:
        while not _shutdown.is_set():
            polled = False
            for message in consumer:
                polled = True
                record = decode_value(message.value)
                if record is None:
                    _stats["decode_errors"] += 1
                    continue
                try:
                    row = map_quarantine_record(record)
                except Exception as exc:  # noqa: BLE001
                    _stats["map_errors"] += 1
                    logger.warning("map_failed", extra={"error": str(exc)})
                    continue
                sink.add(row)
                _stats["records_consumed"] += 1
                _stats["rows_appended"] = sink.rows_appended
                _stats["flushes"] = sink.flushes
            sink.maybe_flush()
            _stats["rows_appended"] = sink.rows_appended
            _stats["flushes"] = sink.flushes
            if not polled:
                time.sleep(0.05)
    finally:
        sink.flush()
        consumer.close()
        logger.info("lakehouse_dlq_writer_stopped", extra=dict(_stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
