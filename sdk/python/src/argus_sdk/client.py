"""HTTP client for ARGUS api-gateway REST."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from argus_sdk.errors import ArgusAPIError, ArgusAuthError
from argus_sdk.models import IncidentSummary, RetrainResponse, TelemetryQueryResult


class ArgusClient:
    """Typed REST client for the Phase 9 api-gateway.

    Auth (first match wins):
      - ``api_key`` / ``ARGUS_API_KEY`` → ``X-API-Key``
      - ``token`` / ``ARGUS_TOKEN`` → ``Authorization: Bearer``
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("ARGUS_GATEWAY_URL")
            or os.environ.get("ARGUS_API_URL")
            or "http://localhost:8099"
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("ARGUS_API_KEY")
        self.token = token or os.environ.get("ARGUS_TOKEN")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers=self._auth_headers(),
        )

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ArgusClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        res = self._client.request(method, path, **kwargs)
        if res.status_code in (401, 403):
            raise ArgusAuthError(res.text or res.reason_phrase)
        if res.status_code >= 400:
            raise ArgusAPIError(res.status_code, res.text or res.reason_phrase)
        if not res.content:
            return None
        ctype = res.headers.get("content-type", "")
        if "json" in ctype:
            return res.json()
        return res.text

    def ping(self) -> dict[str, Any]:
        return self._request("GET", "/v1/ping")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def query_telemetry(self, sql: str, *, limit: int = 50) -> TelemetryQueryResult:
        data = self._request(
            "POST",
            "/v1/telemetry/query",
            json={"sql": sql, "limit": limit},
        )
        return TelemetryQueryResult.model_validate(data)

    def list_incidents(self, *, status: str | None = None) -> list[IncidentSummary]:
        params = {"status": status} if status else None
        data = self._request("GET", "/v1/incidents", params=params)
        items = (data or {}).get("incidents") or []
        return [IncidentSummary.model_validate(i) for i in items]

    def acknowledge_incident(
        self, incident_id: str, *, note: str = ""
    ) -> IncidentSummary:
        data = self._request(
            "POST",
            f"/v1/incidents/{incident_id}/acknowledge",
            json={"note": note},
        )
        return IncidentSummary.model_validate((data or {}).get("incident") or data)

    def resolve_incident(self, incident_id: str) -> IncidentSummary:
        data = self._request("POST", f"/v1/incidents/{incident_id}/resolve")
        return IncidentSummary.model_validate((data or {}).get("incident") or data)

    def trigger_retraining(
        self, *, reason: str = "", tags: dict[str, str] | None = None
    ) -> RetrainResponse:
        data = self._request(
            "POST",
            "/v1/retraining:trigger",
            json={"reason": reason, "tags": tags or {}},
        )
        return RetrainResponse.model_validate(data)

    @contextmanager
    def stream_telemetry(
        self, *, vehicle_id: str | None = None
    ) -> Iterator[Iterator[dict[str, Any]]]:
        """Context manager yielding an iterator of NDJSON telemetry events."""
        params = {}
        if vehicle_id:
            params["vehicle_id"] = vehicle_id
        with self._client.stream(
            "GET",
            "/v1/telemetry/stream",
            params=params or None,
            headers={"Accept": "application/json"},
            timeout=None,
        ) as res:
            if res.status_code in (401, 403):
                raise ArgusAuthError(res.text or res.reason_phrase)
            if res.status_code >= 400:
                raise ArgusAPIError(res.status_code, res.text or res.reason_phrase)

            def _iter() -> Iterator[dict[str, Any]]:
                for line in res.iter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

            yield _iter()
