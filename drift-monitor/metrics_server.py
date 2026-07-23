"""HTTP /health and Prometheus /metrics for drift-monitor."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest


class DriftMetrics:
    """Prometheus gauges for feature drift scores and pipeline health."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.feature_drift_score = Gauge(
            "argus_drift_feature_score",
            "Latest drift score per feature (KS statistic or Evidently score)",
            ["feature"],
            registry=self.registry,
        )
        self.baseline_staleness = Gauge(
            "argus_drift_baseline_staleness_seconds",
            "Seconds since golden baseline was frozen",
            registry=self.registry,
        )
        self.records_evaluated = Gauge(
            "argus_drift_records_evaluated",
            "Total validated telemetry records evaluated",
            registry=self.registry,
        )
        self.incidents_published = Gauge(
            "argus_drift_incidents_published",
            "Total IncidentEvents published to incidents.raw",
            registry=self.registry,
        )
        self.windows_analyzed = Gauge(
            "argus_drift_windows_analyzed",
            "Total sliding windows analyzed",
            registry=self.registry,
        )

    def set_feature_scores(self, scores: dict[str, float]) -> None:
        for feature, score in scores.items():
            self.feature_drift_score.labels(feature=feature).set(float(score))


def start_http_server(
    port: int,
    *,
    metrics: DriftMetrics,
    stats_provider: Callable[[], dict[str, Any]],
    ready_provider: Callable[[], bool],
) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/health", "/healthz", "/"):
                # Liveness always 200; readiness is the ready flag (baseline/Kafka).
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

            if self.path == "/metrics":
                payload = generate_latest(metrics.registry)
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if self.path.startswith("/reports"):
                self.send_response(404)
                self.end_headers()
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
