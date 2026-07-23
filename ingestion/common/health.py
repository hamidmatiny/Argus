"""HTTP /health + Prometheus /metrics for ingestion services."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        generate_latest,
    )

    _REG = CollectorRegistry()
    EVENTS = Counter(
        "argus_ingestion_events_total",
        "Ingestion pipeline events",
        ["service", "result"],
        registry=_REG,
    )
    READY_G = Gauge(
        "argus_ingestion_ready",
        "1 when the service reports ready",
        ["service"],
        registry=_REG,
    )
    _HAS_PROM = True
except ImportError:  # pragma: no cover
    _HAS_PROM = False
    EVENTS = None  # type: ignore[assignment]
    READY_G = None  # type: ignore[assignment]
    _REG = None  # type: ignore[assignment]


def start_health_server(
    port: int,
    *,
    stats_provider: Callable[[], dict[str, Any]] | None = None,
    ready_provider: Callable[[], bool] | None = None,
    service_name: str = "ingestion",
) -> HTTPServer:
    """Start a daemon HTTP server exposing GET /health, /healthz, /metrics."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/metrics" and _HAS_PROM:
                ready = True if ready_provider is None else bool(ready_provider())
                READY_G.labels(service=service_name).set(1.0 if ready else 0.0)
                if stats_provider is not None:
                    stats = stats_provider()
                    # Best-effort mirror of common counter keys into Prometheus.
                    for key, label in (
                        ("published", "published"),
                        ("consumed", "consumed"),
                        ("normalized", "normalized"),
                        ("emitted", "published"),
                    ):
                        if key in stats:
                            # Gauges via counter absolute set is awkward; expose as gauge-like
                            # by using unlabeled absolute values in a fresh text blob below.
                            pass
                body = generate_latest(_REG)
                # Append absolute stats as gauges for dashboards.
                extra = []
                if stats_provider is not None:
                    for k, v in stats_provider().items():
                        if isinstance(v, (int, float)):
                            extra.append(
                                f'argus_ingestion_stat{{service="{service_name}",stat="{k}"}} {float(v)}'
                            )
                if extra:
                    body = body + ("\n".join(extra) + "\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path not in ("/health", "/healthz", "/"):
                self.send_response(404)
                self.end_headers()
                return

            # /health is liveness (always 200 once the HTTP server is up).
            # Readiness is exposed via the ready boolean in the JSON body.
            ready = True if ready_provider is None else bool(ready_provider())
            body_obj: dict[str, Any] = {
                "status": "ok" if ready else "starting",
                "ready": ready,
            }
            if stats_provider is not None:
                body_obj["stats"] = stats_provider()
            body = json.dumps(body_obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    server = HTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
