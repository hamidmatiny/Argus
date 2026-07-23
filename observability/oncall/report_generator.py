#!/usr/bin/env python3
"""Lightweight on-call webhook sink + printable incident report for demos.

Receives Alertmanager webhooks (default + drift channels), stores recent
alerts, and renders a human-readable on-call report (portfolio walkthrough
artifact). Inspired by vanguard's alert_handler SLA-breach printout.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ADDR = os.getenv("ONCALL_ADDR", "0.0.0.0:8100")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
INCIDENT_INBOX_URL = os.getenv(
    "INCIDENT_MOCK_INBOX_URL", "http://incident-engine:8098/webhooks/mock/inbox"
)
MAX_ALERTS = int(os.getenv("ONCALL_MAX_ALERTS", "200"))

_lock = threading.Lock()
_alerts: deque[dict[str, Any]] = deque(maxlen=MAX_ALERTS)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _prom_query(expr: str) -> float | None:
    url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.request.quote(expr)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            payload = json.loads(resp.read().decode())
        results = payload.get("data", {}).get("result", [])
        if not results:
            return None
        return float(results[0]["value"][1])
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, IndexError):
        return None


def _fetch_json(url: str) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def record_webhook(channel: str, body: dict[str, Any]) -> None:
    entry = {
        "received_at": _now(),
        "channel": channel,
        "status": body.get("status"),
        "receiver": body.get("receiver"),
        "alerts": body.get("alerts", []),
        "commonLabels": body.get("commonLabels", {}),
        "commonAnnotations": body.get("commonAnnotations", {}),
    }
    with _lock:
        _alerts.appendleft(entry)
    print(
        json.dumps(
            {
                "msg": "alertmanager_webhook",
                "channel": channel,
                "status": entry["status"],
                "alert_count": len(entry["alerts"]),
            }
        ),
        flush=True,
    )


def build_report() -> str:
    qa = _prom_query("argus:qa_pass_ratio")
    drift = _prom_query("argus:drift_score_avg")
    open_breakers = _prom_query("argus:breakers_open")
    trip_rate = _prom_query("argus:breaker_trip_rate")
    ingest = _prom_query("argus:ingestion_events_per_second")

    inbox = _fetch_json(INCIDENT_INBOX_URL) or {}
    mock_items = inbox.get("inbox", []) if isinstance(inbox, dict) else []

    with _lock:
        recent = list(_alerts)[:20]

    lines = [
        "=" * 72,
        "ARGUS ON-CALL INCIDENT REPORT",
        f"Generated: {_now()}",
        "=" * 72,
        "",
        "SLO SNAPSHOT",
        "-" * 72,
        f"  Ingestion throughput : {_fmt(ingest, 'events/s')}",
        f"  QA pass ratio        : {_fmt_pct(qa)}  (SLO ≥ 99%)",
        f"  Avg drift score      : {_fmt(drift)}  (warn > 0.2)",
        f"  Open breakers        : {_fmt(open_breakers, 'vehicles')}",
        f"  Breaker trip rate    : {_fmt(trip_rate, '/s')}",
        "",
        "SLA BREACH EVALUATION (vanguard-style)",
        "-" * 72,
    ]

    breaches: list[str] = []
    if qa is not None and qa < 0.99:
        breaches.append(f"QA pass ratio {qa:.4f} below 0.99 SLO")
    if drift is not None and drift > 0.2:
        breaches.append(f"Drift score {drift:.4f} exceeds 0.2 warning threshold")
    if open_breakers is not None and open_breakers > 0:
        breaches.append(f"{int(open_breakers)} circuit breaker(s) OPEN")
    if trip_rate is not None and trip_rate > 0.05:
        breaches.append(f"Escalation storm: trip rate {trip_rate:.4f}/s")

    if breaches:
        lines.append("  STATUS: BREACH")
        for b in breaches:
            lines.append(f"    • {b}")
    else:
        lines.append("  STATUS: CLEAR — no SLO / drift / breaker breaches detected")

    lines.extend(["", "RECENT ALERTMANAGER WEBHOOKS", "-" * 72])
    if not recent:
        lines.append("  (none yet)")
    else:
        for e in recent:
            labels = e.get("commonLabels") or {}
            name = labels.get("alertname", "(group)")
            lines.append(
                f"  [{e['received_at']}] channel={e['channel']} "
                f"status={e.get('status')} alert={name} n={len(e.get('alerts') or [])}"
            )

    lines.extend(["", "INCIDENT-ENGINE MOCK WEBHOOK INBOX (tail)", "-" * 72])
    if not mock_items:
        lines.append("  (empty)")
    else:
        for item in list(mock_items)[-10:]:
            lines.append(f"  {json.dumps(item, default=str)[:200]}")

    lines.extend(["", "=" * 72, "End of report", ""])
    return "\n".join(lines)


def _fmt(v: float | None, unit: str = "") -> str:
    if v is None:
        return "n/a"
    suffix = f" {unit}" if unit else ""
    return f"{v:.4g}{suffix}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.2f}%"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/healthz"):
            self._write(200, b'{"status":"ok","service":"oncall-reporter"}\n', "application/json")
            return
        if self.path in ("/report", "/report.txt"):
            text = build_report().encode()
            self._write(200, text, "text/plain; charset=utf-8")
            return
        if self.path == "/alerts":
            with _lock:
                payload = json.dumps({"alerts": list(_alerts)}, indent=2).encode()
            self._write(200, payload, "application/json")
            return
        self._write(404, b'{"error":"not found"}\n', "application/json")

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/webhook/default":
            record_webhook("default", self._read_json())
            self._write(200, b'{"accepted":true}\n', "application/json")
            return
        if self.path == "/webhook/drift":
            record_webhook("drift", self._read_json())
            self._write(200, b'{"accepted":true}\n', "application/json")
            return
        self._write(404, b'{"error":"not found"}\n', "application/json")


def main() -> None:
    host, _, port_s = ADDR.partition(":")
    port = int(port_s or "8100")
    server = ThreadingHTTPServer((host or "0.0.0.0", port), Handler)
    print(json.dumps({"msg": "oncall_listen", "addr": f"{host}:{port}"}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
