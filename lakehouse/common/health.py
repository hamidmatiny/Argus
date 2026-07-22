"""Minimal /health HTTP server for lakehouse writers."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable


def start_health_server(
    port: int,
    *,
    stats_provider: Callable[[], dict[str, Any]],
    ready_provider: Callable[[], bool],
) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/health", "/healthz", "/"):
                ready = ready_provider()
                body = json.dumps(
                    {
                        "status": "ok" if ready else "starting",
                        "ready": ready,
                        "stats": stats_provider(),
                    }
                ).encode()
                self.send_response(200 if ready else 503)
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
