# api-gateway

North-south **API gateway** for ARGUS: authn/authz (OPA), rate limiting, routing to internal services, and public/OpenAPI surfaces for dashboard, SDK, and CLI.

**Status:** Scaffold only — implemented in a later phase.

**Language:** Go

**Responsibilities (planned):**
- JWT / mTLS ingress and OPA policy enforcement
- Route aggregation for incidents, telemetry query, and copilot
- Structured JSON logging and `/healthz` / `/readyz`
