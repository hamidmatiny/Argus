# Contributing to ARGUS

Thanks for helping build ARGUS. This repository is developed in **explicit phases** so each layer stays reviewable and production-shaped.

## Phase-based build history

ARGUS is not a greenfield dump of features. Work lands in numbered phases:

| Phase | Focus | Typical deliverables |
|-------|--------|----------------------|
| **0** | Scaffolding | Monorepo layout, docs, compose Redpanda, CI skeleton, Go workspace stubs |
| **1** | Contracts | Schemas in `shared/`, `make proto`, topic naming, SDK stubs |
| **2+** | Data plane | Ingestion (Ray), Flink QA, Iceberg lakehouse |
| **N** | Control & MLOps | Dagster, MLflow, drift-monitor |
| **N** | Ops loop | incident-engine, api-gateway + OPA, observability, dashboard |
| **N** | Copilot & polish | ai-copilot, e2e, Helm/ArgoCD/Terraform hardening |

Commit messages must use the phase prefix:

```text
phase-N: short description
```

Example: `phase-0: add Redpanda to docker-compose`.

If a change spans phases, prefer splitting PRs; if inseparable, use the **lowest** phase that the change primarily advances and call out follow-ups in the PR body.

## Before you open a PR

1. Read [ARCHITECTURE.md](./ARCHITECTURE.md) and the component `README.md` you touch.
2. Follow `.cursor/rules/` (monorepo + language style).
3. For **new services**, complete the definition of done:
   - `README.md`
   - `Dockerfile`
   - Health endpoints (`/healthz`, `/readyz` when needed)
   - Structured JSON logging
   - Tests
4. Run locally what exists: `make lint`, `make test`, and `make up` / `make down` if you touch compose.
5. Update `.env.example` when you introduce new configuration.
6. Do not commit secrets, real credentials, or production data.

## Local development

```bash
cp .env.example .env
make up      # Redpanda today; more services in later phases
make logs
make down
```

Production path (later phases): Terraform → EKS → Helm → Argo CD. Keep local and prod **image/config parity** where possible.

## Code review expectations

- Small PRs mapped to one component or one phase concern
- Clear data-contract impact (topics, schemas, Iceberg tables)
- CI green once real jobs exist for your language
- No drive-by refactors unrelated to the phase goal

## License

By contributing, you agree that your contributions are licensed under the Apache License 2.0 (see [LICENSE](./LICENSE)).
