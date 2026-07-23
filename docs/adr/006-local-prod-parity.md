# ADR 006 — Local / production parity

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 0, 12, 14

## Context

Portfolio platforms often demo on compose then hand-wave production. Hiring managers notice when local and prod are different products.

## Decision

- **One image per service** used in compose and Helm.
- **Same topic names, Avro schemas, health ports, and env var shape.**
- Local substitutes: Redpanda↔MSK, MinIO/REST↔S3/Glue, Keycloak in compose ↔ corporate IdP.
- Infra: Terraform (VPC/EKS/MSK/Iceberg) + Helm + Argo CD app-of-apps; `terraform validate` / `helm lint` in Makefile, never silent apply.

## Consequences

- Compose is a truthful slice of prod, not a toy rewrite.
- CI builds every Dockerfile and smokes `/health`.
- Docs must call out the few intentional swaps (brokers, catalog type).
