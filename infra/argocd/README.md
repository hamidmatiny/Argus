# infra/argocd

GitOps manifests for ARGUS.

- `root/application.yaml` — app-of-apps entrypoint
- `apps/` — one Argo CD `Application` per Helm chart
- [`PROMOTION.md`](./PROMOTION.md) — dev → staging → prod

```bash
kubectl apply -f root/application.yaml
```
