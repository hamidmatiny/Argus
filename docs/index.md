# ARGUS documentation

**ARGUS** is a production-shaped fleet telemetry platform: Kafka-compatible streaming, Ray + Flink QA, Iceberg lakehouse, Dagster/MLflow, drift → OPA incidents, OpenTelemetry, operator dashboard, and a read-only AI copilot — all runnable locally with one compose command.

## Start here

| Time | Page |
|------|------|
| 5 minutes | [Getting Started](getting-started.md) |
| 5 minutes live | [Demo Script](DEMO_SCRIPT.md) |
| Portfolio deep-dive | [Case Study](CASE_STUDY.md) |
| Design north star | [Architecture](architecture.md) |
| Why we chose X | [ADRs](adr/index.md) |
| On-call | [Operations Runbook](operations-runbook.md) |

```bash
cp .env.example .env
# set NEXTAUTH_SECRET=$(openssl rand -base64 32)
docker compose up -d --build
```

Then open [http://localhost:3002](http://localhost:3002) (dashboard) and [http://localhost:3001](http://localhost:3001) (Grafana).
