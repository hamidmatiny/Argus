"""CLI: ARGUS stream-processor QA gate (--engine=local|flink)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Ensure stream-processor root is on sys.path when executed as a script.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_REPO = _ROOT.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from local_runner.runner import run_local  # noqa: E402
from validation.metrics import QA_QUARANTINE_RATE_THRESHOLD, QA_WINDOW_EVENTS  # noqa: E402

_stats: dict[str, int] = {}
_ready = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "taskName",
            }:
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def start_health(port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/metrics":
                from metrics_prom import observe_stats, render

                observe_stats(_stats, ready=_ready)
                body, ctype = render()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path not in ("/health", "/healthz", "/"):
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(
                {"status": "ok" if _ready else "starting", "ready": _ready, "stats": _stats}
            ).encode()
            self.send_response(200 if _ready else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ARGUS stream-processor QA gate")
    p.add_argument(
        "--engine",
        choices=("local", "flink"),
        default=os.getenv("QA_ENGINE", "local"),
        help="Execution engine (local = pure Python; flink = PyFlink job)",
    )
    p.add_argument(
        "--broker",
        default=os.getenv("KAFKA_BROKERS", "localhost:19092"),
    )
    p.add_argument(
        "--source-topic",
        default=os.getenv("QA_SOURCE_TOPIC", "telemetry.normalized"),
    )
    p.add_argument(
        "--validated-topic",
        default=os.getenv("QA_VALIDATED_TOPIC", "telemetry.validated"),
    )
    p.add_argument(
        "--quarantine-topic",
        default=os.getenv("QA_QUARANTINE_TOPIC", "telemetry.quarantine"),
    )
    p.add_argument(
        "--metrics-topic",
        default=os.getenv("QA_METRICS_TOPIC", "telemetry.qa_metrics"),
    )
    p.add_argument(
        "--group-id",
        default=os.getenv("QA_KAFKA_GROUP_ID", "argus-stream-processor"),
    )
    p.add_argument(
        "--schema-registry",
        default=os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:18081"),
    )
    p.add_argument(
        "--window-size",
        type=int,
        default=int(os.getenv("QA_WINDOW_EVENTS", str(QA_WINDOW_EVENTS))),
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=float(
            os.getenv("QA_QUARANTINE_RATE_THRESHOLD", str(QA_QUARANTINE_RATE_THRESHOLD))
        ),
    )
    p.add_argument(
        "--health-port",
        type=int,
        default=int(os.getenv("QA_HEALTH_PORT", "8093")),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    global _ready, _stats
    args = build_parser().parse_args(argv)
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    try:
        from otel_setup import init_tracer

        init_tracer("stream-processor")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("argus.stream_processor").warning(
            "otel_init_failed", extra={"error": str(exc)}
        )
    start_health(args.health_port)
    _ready = True
    logging.getLogger("argus.stream_processor").info(
        "stream_processor_starting",
        extra={"engine": args.engine, "broker": args.broker},
    )

    common = dict(
        brokers=args.broker,
        source_topic=args.source_topic,
        validated_topic=args.validated_topic,
        quarantine_topic=args.quarantine_topic,
        metrics_topic=args.metrics_topic,
        group_id=args.group_id,
        window_size=args.window_size,
    )

    if args.engine == "local":
        _stats.update(
            {
                "consumed": 0,
                "validated": 0,
                "quarantined": 0,
                "metrics_emitted": 0,
                "decode_failures": 0,
            }
        )
        run_local(
            **common,
            schema_registry_url=args.schema_registry,
            threshold=args.threshold,
            stats=_stats,
        )
        return 0

    from flink_job.job import run_flink

    run_flink(**common, parallelism=int(os.getenv("FLINK_PARALLELISM", "1")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
