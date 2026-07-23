# Promotion flow (dev → staging → prod)

ARGUS uses **GitOps**: the desired state lives in this repo under `infra/helm/`
and `infra/argocd/`. Argo CD continuously reconciles clusters to that state.

## Topology

```
PR merges to main
        │
        ▼
┌───────────────────┐
│ argus-root (App)  │  infra/argocd/root/application.yaml
│  app-of-apps      │
└─────────┬─────────┘
          │ manages
          ▼
┌───────────────────┐
│ infra/argocd/apps │  one Application per Helm chart
└─────────┬─────────┘
          │ syncs
          ▼
┌───────────────────┐
│ infra/helm/<svc>  │  chart + values/<env>.yaml
└───────────────────┘
```

## Environments

| Env | Cluster (typical) | Values overlay | Sync |
|-----|-------------------|----------------|------|
| **dev** | `argus-dev` EKS | `values/dev.yaml` | Auto-sync on `main` |
| **staging** | `argus-staging` EKS | `values/staging.yaml` | Auto-sync from `main` after CI green |
| **prod** | `argus-prod` EKS | `values/prod.yaml` | **Manual** sync / PR to `releases/prod` |

Each environment cluster has its own Argo CD (or ApplicationSet with
cluster generators). The manifests in this repo default to **dev** value
files; staging/prod Applications override `helm.valueFiles` (or use an
ApplicationSet `env` parameter).

## Promotion steps

1. **Develop in a feature branch** — change Helm values / chart templates.
2. **Open a PR to `main`** — CI runs `helm lint`, `terraform validate`, chart
   unit smoke (`helm template`).
3. **Merge → Argo CD syncs `dev`** — automated prune + self-heal.
4. **Promote to staging** — either:
   - merge the same commit and let staging Applications pick `values/staging.yaml`, or
   - open a PR that only bumps image tags in `values/staging.yaml`.
5. **Promote to prod** — PR that updates `values/prod.yaml` image digests /
   replica counts. Require two reviewers. Argo CD **does not** auto-sync prod
   (set `syncPolicy.automated: null` on prod Applications); an operator clicks
   **Sync** after the PR merges, or a release Application tracks the
   `releases/prod` branch.

## Rollback

- `argocd app rollback argus-<chart>` or revert the Git commit and let
  self-heal apply.
- Terraform changes (MSK, EKS, IAM) are **not** rolled back by Argo CD —
  use `terraform plan` in `infra/terraform/environments/<env>` and a separate
  change management process.

## Image promotion

Build once in CI → push immutable tag (`sha-<gitsha>`) to GHCR/ECR → update
only the `image.tag` field in the target env values file. Never retag
`latest` for prod.
