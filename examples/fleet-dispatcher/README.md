# Fleet dispatcher example

Tiny third-party style service that uses **`argus-sdk`** to:

1. Call the api-gateway (`ping`, list open incidents)
2. Ingest a few synthetic `TelemetryEvent`s onto `telemetry.raw` via `IngestClient`

## Run

```bash
# Install SDK (gateway + ingest extras)
pip install -e 'sdk/python[ingest]'

# Stack must be up (gateway + Redpanda + schema registry)
export ARGUS_API_KEY=demo-operator
export ARGUS_GATEWAY_URL=http://localhost:8099
export ARGUS_KAFKA_BROKERS=localhost:19092
export ARGUS_SCHEMA_REGISTRY_URL=http://localhost:18081

python examples/fleet-dispatcher/main.py
python examples/fleet-dispatcher/main.py --skip-ingest   # gateway only
```

This is the “here’s how a third party integrates” proof point for the platform.
