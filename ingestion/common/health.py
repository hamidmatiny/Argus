"""Minimal HTTP /health server for container probes."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable


def start_health_server(
    port: int,
    *,
    stats_provider: Callable[[], dict[str, Any]] | None = None,
    ready_provider: Callable[[], bool] | None = None,
) -> HTTPServer:
    """Start a daemon HTTP server exposing GET /health and /healthz."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ("/health", "/healthz", "/"):
                self.send_response(404)
                self.end_headers()
                return

            ready = True if ready_provider is None else bool(ready_provider())
            body_obj: dict[str, Any] = {
                "status": "ok" if ready else "starting",
                "ready": ready,
            }
            if stats_provider is not None:
                body_obj["stats"] = stats_provider()
            body = json.dumps(body_obj).encode()
            code = 200 if ready else 503
            self.send_response(code)
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
