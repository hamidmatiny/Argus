"""Unit tests for ArgusClient against a mocked gateway."""

from __future__ import annotations

import httpx
import pytest
import respx

from argus_sdk import ArgusAPIError, ArgusAuthError, ArgusClient


@pytest.fixture
def client() -> ArgusClient:
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    return ArgusClient(
        base_url="http://gateway.test",
        api_key="demo-operator",
        transport=transport,
    )


@respx.mock
def test_list_incidents() -> None:
    respx.get("http://gateway.test/v1/incidents").mock(
        return_value=httpx.Response(
            200,
            json={
                "incidents": [
                    {
                        "incident_id": "esc_1",
                        "vehicle_id": "VH-0001",
                        "status": "INCIDENT_STATUS_OPEN",
                    }
                ]
            },
        )
    )
    with ArgusClient(base_url="http://gateway.test", api_key="demo-viewer") as c:
        items = c.list_incidents(status="open")
    assert len(items) == 1
    assert items[0].incident_id == "esc_1"


@respx.mock
def test_acknowledge_incident() -> None:
    respx.post("http://gateway.test/v1/incidents/esc_1/acknowledge").mock(
        return_value=httpx.Response(
            200,
            json={
                "incident": {
                    "incident_id": "esc_1",
                    "status": "INCIDENT_STATUS_ACKNOWLEDGED",
                }
            },
        )
    )
    with ArgusClient(base_url="http://gateway.test", api_key="demo-operator") as c:
        inc = c.acknowledge_incident("esc_1", note="looking")
    assert inc.status == "INCIDENT_STATUS_ACKNOWLEDGED"


@respx.mock
def test_query_telemetry() -> None:
    respx.post("http://gateway.test/v1/telemetry/query").mock(
        return_value=httpx.Response(
            200,
            json={"columns": ["vehicle_id"], "rows": [{"vehicle_id": "VH-1"}], "row_count": 1},
        )
    )
    with ArgusClient(base_url="http://gateway.test", api_key="demo-viewer") as c:
        result = c.query_telemetry("SELECT 1", limit=10)
    assert result.row_count == 1


@respx.mock
def test_trigger_retraining() -> None:
    respx.post("http://gateway.test/v1/retraining:trigger").mock(
        return_value=httpx.Response(
            200, json={"run_id": "run-1", "status": "STARTED", "message": "ok"}
        )
    )
    with ArgusClient(base_url="http://gateway.test", api_key="demo-operator") as c:
        out = c.trigger_retraining(reason="drift")
    assert out.run_id == "run-1"


@respx.mock
def test_auth_error() -> None:
    respx.get("http://gateway.test/v1/incidents").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    with ArgusClient(base_url="http://gateway.test") as c:
        with pytest.raises(ArgusAuthError):
            c.list_incidents()


@respx.mock
def test_api_error() -> None:
    respx.post("http://gateway.test/v1/telemetry/query").mock(
        return_value=httpx.Response(500, text="boom")
    )
    with ArgusClient(base_url="http://gateway.test", api_key="demo-viewer") as c:
        with pytest.raises(ArgusAPIError) as ei:
            c.query_telemetry("SELECT 1")
    assert ei.value.status_code == 500


@respx.mock
def test_stream_telemetry_ndjson() -> None:
    def _stream(request: httpx.Request) -> httpx.Response:
        body = (
            b'{"event":{"vehicle_id":"VH-0001"}}\n'
            b'{"event":{"vehicle_id":"VH-0002"}}\n'
        )
        return httpx.Response(200, content=body)

    respx.get("http://gateway.test/v1/telemetry/stream").mock(side_effect=_stream)
    with ArgusClient(base_url="http://gateway.test", api_key="demo-viewer") as c:
        with c.stream_telemetry() as events:
            rows = list(events)
    assert len(rows) == 2
    assert rows[0]["event"]["vehicle_id"] == "VH-0001"
