# infra/helm

One chart per deployable ARGUS service, plus `observability` (kube-prometheus-stack).

```bash
helm lint ingestion
helm template smoke ingestion -f ingestion/values.yaml -f ingestion/values/dev.yaml
```

NetworkPolicies are **on by default** — egress only to DNS, declared peer
services, and `networkPolicy.egressCIDRs` (set to your VPC CIDR in each env).
