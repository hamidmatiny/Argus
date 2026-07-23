# ARGUS Python SDK (`argus-sdk`)

Typed client for the Phase 9 **api-gateway**, plus a drop-in Kafka
`IngestClient` that validates against the Phase 1 `TelemetryEvent` contract.

## What it does

See the narrative sections below for responsibilities and scope.

## Architecture

See topology / flow / ports sections below.

## Testing

See the Tests section below.

## Install

```bash
# Gateway client only
pip install -e sdk/python

# + Kafka ingest (Confluent Avro → telemetry.raw)
pip install -e 'sdk/python[ingest]'

# Dev / tests
pip install -e 'sdk/python[dev]'
pytest sdk/python/tests -q
```

## Quickstart — gateway

```python
from argus_sdk import ArgusClient

with ArgusClient(api_key="demo-operator") as client:
    print(client.ping())
    for inc in client.list_incidents(status="open"):
        print(inc.incident_id, inc.vehicle_id)
    client.acknowledge_incident("esc_1", note="on it")
    client.trigger_retraining(reason="manual")

    with client.stream_telemetry() as events:
        for msg in events:
            print(msg)
            break
```

Env defaults: `ARGUS_GATEWAY_URL=http://localhost:8099`, `ARGUS_API_KEY` or
`ARGUS_TOKEN` (Bearer).

## Quickstart — ingest (3 lines)

```python
from datetime import datetime, timezone
from argus_sdk import IngestClient, TelemetryEvent, DeviceType, SensorStatus

event = TelemetryEvent(
    vehicle_id="VH-0001234",
    trip_id="demo-trip",
    timestamp=datetime.now(tz=timezone.utc),
    gps_lat=37.77, gps_lon=-122.42,
    speed_mph=28.0, brake_pressure=0.2, lidar_temp_c=41.0,
    compute_load_pct=40.0, sensor_status=SensorStatus.OK,
    hardware_version="v1", device_type=DeviceType.SIMULATOR,
)
with IngestClient() as ingest:   # brokers via ARGUS_KAFKA_BROKERS
    ingest.publish(event)
```

## Auth

| Mode | How |
|------|-----|
| Demo API key | `ArgusClient(api_key="demo-viewer\|demo-operator\|demo-admin")` |
| OIDC JWT | `ArgusClient(token="<access_token>")` |