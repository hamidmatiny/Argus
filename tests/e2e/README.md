# End-to-end, load, and chaos tests

These suites are **not** run on every PR (too slow). They run on a schedule
and via `workflow_dispatch`.

## Full-stack smoke (`smoke.sh`)

Boots docker compose, waits for health endpoints, lets the simulator run
(~60s), then asserts via the api-gateway:

- Core service `/health` (and dashboard `/login`) are green
- `/v1/ping` succeeds
- Telemetry landed in the lakehouse (`POST /v1/telemetry/query`)
- At least one QA rejection signal (quarantine rows and/or metrics)

```bash
chmod +x tests/e2e/smoke.sh
./tests/e2e/smoke.sh
# SIM_SECONDS=90 E2E_STRICT=1 ./tests/e2e/smoke.sh
```

Workflow: `.github/workflows/e2e-nightly.yml`

## Load (`load/gateway.js`)

k6 script against the gateway. Pass/fail on latency SLO (`ping` p95 < 500ms)
and error rate < 5%.

```bash
k6 run -e GATEWAY_URL=http://localhost:8099 -e API_KEY=demo-viewer \
  -e VUS=10 -e DURATION=2m tests/e2e/load/gateway.js
```

Workflow: `.github/workflows/load-nightly.yml`

## Chaos (`chaos.sh`)

SIGKILL `stream-processor` (override with `CHAOS_SERVICE`) and assert health
comes back while the gateway stays up.

```bash
chmod +x tests/e2e/chaos.sh
# stack already up:
./tests/e2e/chaos.sh
```

Workflow: `.github/workflows/chaos-nightly.yml`
