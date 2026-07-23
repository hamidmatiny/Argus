# api-gateway

North-south API edge for ARGUS. **Phase 8 stub**: `/health`, Prometheus
`/metrics`, and OpenTelemetry traces to the platform collector. OPA authz and
full routing land in a later phase.

| Path | Purpose |
|------|---------|
| `GET /health` | Liveness |
| `GET /metrics` | Prometheus (`argus_gateway_*`) |
| `GET /v1/ping` | Traced ping for demo spans |

Default listen: `:8099`. Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`.
