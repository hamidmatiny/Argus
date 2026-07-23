# API gateway 403 / auth failures during incident response

## Symptoms

- Dashboard actions fail with 403
- `argusctl incidents ack` returns gateway unauthorized
- Copilot tools that hit the gateway fail while direct incident-engine works

## Likely causes

1. Viewer role used for operator mutations
2. Expired Keycloak token / wrong API key (`demo-viewer` vs `demo-operator`)
3. OPA policy path mismatch after a new route is added

## Investigation steps

1. Confirm role in dashboard session chip
2. Retry with `demo-operator` or operator OIDC user
3. Check api-gateway logs for OPA deny
4. Verify `/v1/ping` still public

## Mitigation

- Re-login as operator/admin
- Rotate demo keys only via `argusctl secrets` patterns for real tokens
- Never embed long-lived admin keys in the copilot prompt

## Citations

- Phase 9 api-gateway OPA policies
- Dashboard auth README
