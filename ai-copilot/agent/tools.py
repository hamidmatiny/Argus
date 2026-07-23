"""Read-only tools for the ARGUS operations agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx
from qdrant_client import QdrantClient

from agent.config import Settings
from agent.guardrails import validate_telemetry_sql
from ingestion.embed import Embedder

ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


def _json_loads_safe(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path.read_text(encoding="utf-8")[:2000]


class ToolBelt:
    def __init__(self, settings: Settings, embedder: Embedder) -> None:
        self.settings = settings
        self.embedder = embedder
        self.qdrant = QdrantClient(url=settings.qdrant_url)
        self._http = httpx.Client(timeout=20.0)

    def close(self) -> None:
        self._http.close()

    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "query_incidents",
                "description": "List incidents from incident-engine. Optional status filter: open|acknowledged|resolved.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "vehicle_id": {"type": "string"},
                    },
                },
            },
            {
                "name": "query_drift_report",
                "description": "Fetch drift-monitor health stats and latest drift signal/report summary.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "query_telemetry",
                "description": "Run a scoped SELECT against telemetry/quarantine via the api-gateway (injection-safe).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["sql"],
                },
            },
            {
                "name": "search_runbooks",
                "description": "Semantic search over ARGUS operations runbooks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "search_similar_incidents",
                "description": "Semantic search over historical IncidentEvents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
        ]

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = {
            "query_incidents": self.query_incidents,
            "query_drift_report": self.query_drift_report,
            "query_telemetry": self.query_telemetry,
            "search_runbooks": self.search_runbooks,
            "search_similar_incidents": self.search_similar_incidents,
        }.get(name)
        if not fn:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(args or {})
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def query_incidents(self, args: dict[str, Any]) -> dict[str, Any]:
        params = {}
        if args.get("status"):
            params["status"] = args["status"]
        res = self._http.get(
            f"{self.settings.incident_engine_url}/incidents", params=params
        )
        res.raise_for_status()
        data = res.json()
        incidents = data.get("incidents") or []
        vehicle = (args.get("vehicle_id") or "").strip()
        if vehicle:
            incidents = [
                i
                for i in incidents
                if str(i.get("vehicle_id", "")).upper() == vehicle.upper()
            ]
        return {"incidents": incidents[:50], "count": len(incidents)}

    def query_drift_report(self, args: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        res = self._http.get(f"{self.settings.drift_monitor_url}/health")
        if res.is_success:
            out["health"] = res.json()
        reports = self.settings.drift_reports_dir
        signal = reports / "latest_drift_signal.json"
        if signal.is_file():
            out["latest_signal"] = _json_loads_safe(signal)
        jsons = sorted(reports.glob("data_drift_*.json"), reverse=True)
        if jsons:
            out["latest_report_file"] = jsons[0].name
            out["latest_report_excerpt"] = str(_json_loads_safe(jsons[0]))[:2000]
        return out or {"warning": "no drift data available"}

    def query_telemetry(self, args: dict[str, Any]) -> dict[str, Any]:
        check = validate_telemetry_sql(str(args.get("sql", "")))
        if not check.ok:
            return {"error": check.reason}
        limit = int(args.get("limit") or 50)
        limit = max(1, min(limit, 100))
        res = self._http.post(
            f"{self.settings.gateway_url}/v1/telemetry/query",
            headers={
                "X-API-Key": self.settings.gateway_api_key,
                "Content-Type": "application/json",
            },
            json={"sql": check.sanitized, "limit": limit},
        )
        if res.status_code >= 400:
            return {"error": f"gateway {res.status_code}", "body": res.text[:500]}
        return res.json()

    def search_runbooks(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._search(
            self.settings.collection_runbooks,
            str(args.get("query", "")),
            int(args.get("limit") or 4),
        )

    def search_similar_incidents(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._search(
            self.settings.collection_incidents,
            str(args.get("query", "")),
            int(args.get("limit") or 5),
        )

    def _search(self, collection: str, query: str, limit: int) -> dict[str, Any]:
        if not query.strip():
            return {"error": "empty query"}
        vec = self.embedder.embed_one(query)
        try:
            hits = self.qdrant.search(
                collection_name=collection,
                query_vector=vec,
                limit=max(1, min(limit, 10)),
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": f"qdrant: {exc}", "hits": []}
        return {
            "hits": [
                {
                    "score": h.score,
                    "text": (h.payload or {}).get("text", "")[:1500],
                    "metadata": {
                        k: v for k, v in (h.payload or {}).items() if k != "text"
                    },
                }
                for h in hits
            ]
        }
