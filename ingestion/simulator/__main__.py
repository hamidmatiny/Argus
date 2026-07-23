"""CLI entrypoint: fleet telemetry simulator → Kafka."""

from __future__ import annotations

import argparse
import os
import signal
import threading
import time

from ingestion.common.health import start_health_server
from ingestion.common.logging_util import setup_logging
from ingestion.simulator.generator import VehicleTelemetrySimulator, default_vehicle_ids
from ingestion.simulator.kafka_publisher import TelemetryKafkaPublisher

logger = setup_logging("argus.ingestion.simulator", os.getenv("LOG_LEVEL", "INFO"))

_shutdown = threading.Event()


def _handle_signal(signum: int, _frame: object) -> None:
    logger.info("shutdown_signal", extra={"signal": signum})
    _shutdown.set()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ARGUS fleet telemetry simulator (Avro → Kafka).",
    )
    parser.add_argument(
        "--vehicles",
        type=int,
        default=int(os.getenv("SIMULATOR_VEHICLES", "5")),
        help="Number of simulated vehicles",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=float(os.getenv("SIMULATOR_RATE", "10")),
        help="Events per second (aggregate across vehicles)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=float(os.getenv("SIMULATOR_DURATION", "0")),
        help="Seconds to run (0 = forever)",
    )
    parser.add_argument(
        "--failure-rate",
        type=float,
        default=float(os.getenv("SIMULATOR_FAILURE_RATE", "0.05")),
        help="Probability of corruption / anomaly injection [0-1]",
    )
    parser.add_argument(
        "--topic",
        default=os.getenv("SIMULATOR_TOPIC", "telemetry.raw"),
        help="Kafka topic",
    )
    parser.add_argument(
        "--broker",
        default=os.getenv("KAFKA_BROKERS", "localhost:19092"),
        help="Kafka bootstrap brokers",
    )
    parser.add_argument(
        "--schema-registry",
        default=os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:18081"),
        help="Confluent-compatible schema registry URL",
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=int(os.getenv("SIMULATOR_HEALTH_PORT", "8091")),
        help="HTTP /health port",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    return parser


def run(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    vehicle_ids = default_vehicle_ids(args.vehicles)
    simulator = VehicleTelemetrySimulator(
        vehicle_ids=vehicle_ids,
        failure_rate=args.failure_rate,
        seed=args.seed,
    )

    # Liveness first so CI / compose probes work while Kafka is still coming up.
    start_health_server(
        args.health_port,
        stats_provider=lambda: dict(simulator.stats),
        ready_provider=lambda: True,
        service_name="simulator",
    )

    publisher: TelemetryKafkaPublisher | None = None
    while publisher is None and not _shutdown.is_set():
        try:
            publisher = TelemetryKafkaPublisher(
                brokers=args.broker,
                topic=args.topic,
                schema_registry_url=args.schema_registry,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kafka_connect_retry",
                extra={"error": str(exc), "broker": args.broker},
            )
            _shutdown.wait(timeout=2.0)

    if publisher is None:
        logger.error("simulator_aborted_no_kafka")
        return 1

    logger.info(
        "simulator_started",
        extra={
            "vehicles": args.vehicles,
            "rate": args.rate,
            "failure_rate": args.failure_rate,
            "topic": args.topic,
            "broker": args.broker,
            "health_port": args.health_port,
        },
    )

    interval = 1.0 / args.rate if args.rate > 0 else 1.0
    deadline = (
        time.monotonic() + args.duration if args.duration and args.duration > 0 else None
    )

    try:
        while not _shutdown.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                break
            loop_start = time.monotonic()
            record, strategy, raw = simulator.next_message()
            key = (record or {}).get("vehicle_id") or "unknown"
            try:
                publisher.publish(key=key, record=record, raw=raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("publish_failed", extra={"error": str(exc)})
            if strategy:
                logger.warning(
                    "corruption_injected",
                    extra={"strategy": strategy, "vehicle_id": key},
                )
            sleep_for = interval - (time.monotonic() - loop_start)
            if sleep_for > 0:
                _shutdown.wait(timeout=sleep_for)
        publisher.flush()
    finally:
        publisher.close()
        logger.info("simulator_stopped", extra={"stats": dict(simulator.stats)})
    return 0


def main() -> None:
    raise SystemExit(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
