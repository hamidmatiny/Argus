"""CLI entrypoint: Ray Core consumer — telemetry.raw → telemetry.normalized."""

from __future__ import annotations

import argparse
import os
import signal
import threading
import time

import ray

from ingestion.common.health import start_health_server
from ingestion.common.logging_util import setup_logging
from ingestion.ray_consumer.streamer import (
    create_streamer_pool,
    initialize_ray,
    process_partitions_concurrently,
)

logger = setup_logging("argus.ingestion.ray_consumer", os.getenv("LOG_LEVEL", "INFO"))
_shutdown = threading.Event()
_aggregate_stats: dict[str, int] = {
    "consumed": 0,
    "published": 0,
    "quarantined": 0,
    "errors": 0,
    "rounds": 0,
}
_ready = False


def _handle_signal(signum: int, _frame: object) -> None:
    logger.info("shutdown_signal", extra={"signal": signum})
    _shutdown.set()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ARGUS Ray telemetry consumer")
    p.add_argument(
        "--broker",
        default=os.getenv("KAFKA_BROKERS", "localhost:19092"),
    )
    p.add_argument(
        "--source-topic",
        default=os.getenv("INGESTION_RAW_TOPIC", "telemetry.raw"),
    )
    p.add_argument(
        "--dest-topic",
        default=os.getenv("INGESTION_NORMALIZED_TOPIC", "telemetry.normalized"),
    )
    p.add_argument(
        "--group-id",
        default=os.getenv("INGESTION_KAFKA_GROUP_ID", "argus-ingestion"),
    )
    p.add_argument(
        "--partitions",
        type=int,
        default=int(os.getenv("RAY_NUM_PARTITIONS", "4")),
        help="Number of DataStreamer actors (vehicle/camera partitions)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("RAY_BATCH_SIZE", "50")),
    )
    p.add_argument(
        "--num-cpus",
        type=int,
        default=int(os.getenv("RAY_NUM_CPUS", "2")),
    )
    p.add_argument(
        "--schema-registry",
        default=os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:18081"),
    )
    p.add_argument(
        "--health-port",
        type=int,
        default=int(os.getenv("RAY_HEALTH_PORT", "8092")),
    )
    p.add_argument(
        "--dashboard-host",
        default=os.getenv("RAY_DASHBOARD_HOST", "0.0.0.0"),
    )
    p.add_argument(
        "--dashboard-port",
        type=int,
        default=int(os.getenv("RAY_DASHBOARD_PORT", "8265")),
    )
    return p


def run(args: argparse.Namespace) -> int:
    global _ready

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    start_health_server(
        args.health_port,
        stats_provider=lambda: dict(_aggregate_stats),
        ready_provider=lambda: _ready,
    )

    initialize_ray(
        num_cpus=args.num_cpus,
        dashboard_host=args.dashboard_host,
        dashboard_port=args.dashboard_port,
    )
    partition_ids = [f"partition-{i}" for i in range(args.partitions)]
    streamers = create_streamer_pool(
        partition_ids=partition_ids,
        brokers=args.broker,
        source_topic=args.source_topic,
        dest_topic=args.dest_topic,
        group_id=args.group_id,
        schema_registry_url=args.schema_registry,
    )
    _ready = True
    logger.info(
        "ray_consumer_started",
        extra={
            "partitions": args.partitions,
            "source_topic": args.source_topic,
            "dest_topic": args.dest_topic,
            "dashboard_port": args.dashboard_port,
            "health_port": args.health_port,
        },
    )

    try:
        while not _shutdown.is_set():
            results = process_partitions_concurrently(
                streamers, max_messages=args.batch_size
            )
            _aggregate_stats["rounds"] += 1
            for row in results:
                for key in ("consumed", "published", "quarantined", "errors"):
                    # Actor stats are cumulative; track last snapshot via max.
                    _aggregate_stats[key] = max(
                        _aggregate_stats[key], int(row.get(key, 0))
                    )
            time.sleep(0.25)
    finally:
        for streamer in streamers:
            try:
                ray.get(streamer.close.remote())
            except Exception:  # noqa: BLE001
                pass
        ray.shutdown()
        logger.info("ray_consumer_stopped", extra={"stats": dict(_aggregate_stats)})
    return 0


def main() -> None:
    raise SystemExit(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
