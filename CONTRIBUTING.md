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
   - Tests (coverage **≥ 65%** for the package — same gate as CI)
4. Run locally what exists: `make lint`, `make test`, and `make up` / `make down` if you touch compose.
5. Update `.env.example` when you introduce new configuration.
6. Do not commit secrets, real credentials, or production data.

## Local development

```bash
cp .env.example .env
make up
make logs
make down
```

Production path: Terraform → EKS → Helm → Argo CD. Keep local and prod **image/config parity** where possible.

## CI workflows

| Workflow | When | Purpose |
|----------|------|---------|
| [CI](./.github/workflows/ci.yml) | Every PR / push | Path-filtered lint+test per component; Python/Go **≥65%** coverage |
| [Docker Build](./.github/workflows/docker-build.yml) | Dockerfile / service path changes | Build matrix + `/health` smoke, Trivy HIGH/CRITICAL, SBOM (syft) |
| [Semgrep](./.github/workflows/semgrep.yml) | Every PR / push | SAST (owasp / security-audit / ci) |
| [E2E Nightly](./.github/workflows/e2e-nightly.yml) | Nightly + `workflow_dispatch` | Full compose smoke (`tests/e2e/smoke.sh`) |
| [Load Nightly](./.github/workflows/load-nightly.yml) | Nightly + `workflow_dispatch` | k6 gateway latency SLO |
| [Chaos Nightly](./.github/workflows/chaos-nightly.yml) | Nightly + `workflow_dispatch` | Kill stream-processor → assert recovery |

Path filters mean a Go-only PR skips Python jobs (and vice versa). Changing `.github/workflows/ci.yml` or `Makefile` forces the full CI matrix.

**Coverage:** Python jobs use `--cov-fail-under=65`. Go jobs run the full `go test ./...` suite, then hard-gate **≥65%** on the unit-tested packages listed in each job (`COVER_PKGS`). Untested I/O packages are excluded from the percentage gate but still compile/test when present.

## Branch protection (required checks)

Configure GitHub **Settings → Branches → Branch protection** on `main` so merges require:

| Required check name | Workflow job |
|---------------------|--------------|
| `CI success` | Aggregate gate in `ci.yml` (passes when executed jobs pass; skipped path-filtered jobs OK) |
| `Semgrep SAST` | `semgrep.yml` |
| `Build · <service>` *(optional but recommended for release PRs)* | Docker Build matrix — or require the whole **Docker Build** workflow when Dockerfiles change |

Do **not** require `E2E Nightly`, `Load Nightly`, or `Chaos Nightly` on every PR — they are scheduled / manual.

Suggested rules:

- Require pull request before merging
- Require approvals ≥ 1
- Dismiss stale reviews on new commits
- Require status checks to pass (`CI success`, `Semgrep SAST`)
- Restrict force-pushes to `main`

## Code review expectations

- Small PRs mapped to one component or one phase concern
- Clear data-contract impact (topics, schemas, Iceberg tables)
- CI green for the languages you touch
- No drive-by refactors unrelated to the phase goal

## License

By contributing, you agree that your contributions are licensed under the Apache License 2.0 (see [LICENSE](./LICENSE)).
