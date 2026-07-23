"""HTTP /health + Prometheus /metrics for lakehouse writers."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

_REG = CollectorRegistry()
READY_G = Gauge(
    "argus_lakehouse_ready",
    "1 when the lakehouse writer is ready",
    ["writer"],
    registry=_REG,
)
STAT_G = Gauge(
    "argus_lakehouse_stat",
    "Live writer stats mirrored from /health",
    ["writer", "stat"],
    registry=_REG,
)


def start_health_server(
    port: int,
    *,
    stats_provider: Callable[[], dict[str, Any]],
    ready_provider: Callable[[], bool],
    writer_name: str = "writer",
) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/metrics":
                ready = ready_provider()
                READY_G.labels(writer=writer_name).set(1.0 if ready else 0.0)
                for k, v in stats_provider().items():
                    if isinstance(v, (int, float)):
                        STAT_G.labels(writer=writer_name, stat=str(k)).set(float(v))
                body = generate_latest(_REG)
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path in ("/health", "/healthz", "/"):
                # Liveness always 200; ready reflects catalog/Kafka connectivity.
                ready = ready_provider()
                body = json.dumps(
                    {
                        "status": "ok" if ready else "starting",
                        "ready": ready,
                        "stats": stats_provider(),
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
