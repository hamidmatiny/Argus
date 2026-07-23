# Architecture Decision Records

Short records of the biggest technology choices in ARGUS. Each ADR states the context, decision, and consequences.

| ID | Title | Status |
|----|-------|--------|
| [001](001-kafka-redpanda.md) | Kafka API via Redpanda (local) / MSK (prod) | Accepted |
| [002](002-iceberg-lakehouse.md) | Apache Iceberg over Delta / plain Parquet | Accepted |
| [003](003-dagster-vs-airflow.md) | Dagster for lakehouse orchestration | Accepted |
| [004](004-opa-policy-engine.md) | OPA/Rego for incidents + gateway RBAC | Accepted |
| [005](005-read-only-ai-copilot.md) | Read-only AI copilot (no mutating tools) | Accepted |
| [006](006-local-prod-parity.md) | Compose ↔ EKS image/config parity | Accepted |
| [007](007-serverless-etl-alongside-kafka.md) | Serverless ETL demo alongside Kafka/Dagster | Accepted |
