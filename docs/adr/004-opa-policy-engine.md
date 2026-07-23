# ADR 004 — OPA/Rego for policy (incidents + gateway)

**Status:** Accepted  
**Date:** 2026-07  
**Phases:** 7, 9

## Context

Escalation rules (quarantine rate, multi-feature drift, circuit breaker) and API RBAC (viewer/operator/admin) must be auditable and changeable without redeploying opaque `if` trees in Go.

## Decision

- **incident-engine:** evaluate Rego policies over incident inputs; circuit breaker state machine in Go.
- **api-gateway:** OPA for path/method/role authorization alongside Keycloak OIDC / API keys.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Hand-rolled Go policy | Fast to start; becomes unreviewable and hard to share with security |
| Cloud IAM only | Covers infra, not app-level incident escalation or row-scoped SQL |
| Casbin / custom DSL | Viable; OPA has broader policy-as-code mindshare for this portfolio |

## Consequences

- Policies live as `.rego` files next to the engine — reviewable in PRs.
- Need careful input schema stability between Go and Rego.
- Demo keys (`demo-viewer`, `demo-operator`) map cleanly to roles for live demos.
