# ARGUS production infrastructure

Terraform (AWS) + Helm (EKS workloads) + Argo CD (GitOps).

Local development remains **docker-compose**. This tree is the production
footprint: same container images, different substrate (MSK instead of
Redpanda, S3+Glue Iceberg instead of MinIO, EKS instead of Compose).

## Topology

```text
                         ┌─────────────────────────┐
                         │  GitHub (this repo)      │
                         │  infra/helm + argocd     │
                         └────────────┬────────────┘
                                      │ sync
                                      ▼
                         ┌─────────────────────────┐
                         │  Argo CD (app-of-apps)  │
                         │  infra/argocd/root      │
                         └────────────┬────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
   ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
   │ Helm charts │            │ Helm charts │            │ observability│
   │ ingestion…  │            │ api-gateway │            │ kube-prom…  │
   │ dashboard   │            │ incident…   │            └─────────────┘
   └──────┬──────┘            └──────┬──────┘
          │                          │
          └────────────┬─────────────┘
                       ▼
              ┌────────────────┐
              │  EKS (IRSA)    │
              └───────┬────────┘
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
  ┌─────────┐   ┌──────────┐   ┌────────────┐
  │   MSK   │   │ S3 Iceberg│   │ Glue catalog│
  │  Kafka  │   │ warehouse │   │   `fleet`   │
  └─────────┘   └──────────┘   └────────────┘
```

Terraform modules under `terraform/modules/` provision the bottom tier;
Helm/Argo own the top.

| Module | Purpose |
|--------|---------|
| `networking` | VPC, public/private subnets, NAT, IGW |
| `msk` | Managed Kafka (prod stand-in for Redpanda) |
| `iceberg-lakehouse` | S3 + Glue DB — extends [hydra-data-factory](https://github.com/) lakehouse patterns (versioning, SSE, public-access block, prefix IAM → IRSA) |
| `eks` | Cluster + node group + OIDC for IRSA |
| `iam` | Least-privilege IRSA roles (`lakehouse-writer`, `orchestration`, `api-gateway`) |

Environments: `terraform/environments/{dev,staging,prod}/` with **S3 + DynamoDB** remote state.

## Helm charts

One chart per deployable service in `helm/`:

`ingestion`, `stream-processor`, `drift-monitor`, `lakehouse-writer`,
`orchestration`, `incident-engine`, `api-gateway`, `dashboard`,
`observability` (depends on **kube-prometheus-stack**).

Every app chart includes:

- resource requests/limits
- liveness/readiness probes on `/health` (or service-specific ready path)
- **HorizontalPodAutoscaler** for stateless services
- **NetworkPolicy** restricting ingress to the namespace / named peers and
  egress to DNS + declared peers + VPC CIDR (MSK / AWS APIs)

Environment overlays: `helm/<chart>/values/{dev,staging,prod}.yaml`.

## Argo CD

- Root app: `argocd/root/application.yaml` (app-of-apps)
- Child apps: `argocd/apps/*.yaml` (one Application per chart)
- Promotion: see [`argocd/PROMOTION.md`](./argocd/PROMOTION.md)

---

## Validate / plan (no AWS required for validate)

```bash
# Per environment — does not need credentials
cd infra/terraform/environments/dev
terraform init -backend=false
terraform validate

# Same for staging / prod
```

`terraform plan` talks to AWS APIs (and needs a real or LocalStack backend).
**Do not `apply` unless you explicitly intend to create paid resources.**

### Optional LocalStack smoke (plan-shaped)

```bash
# Terminal A
docker run --rm -p 4566:4566 localstack/localstack

# Terminal B
cd infra/terraform/environments/dev
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
# Point provider at LocalStack via a temporary override file, then:
terraform init -backend=false
# Full LocalStack coverage for EKS/MSK is incomplete; prefer `validate` in CI.
terraform validate
```

CI recommendation: run `terraform fmt -check` + `terraform validate` on every PR;
run `plan` only in an authenticated pipeline role.

---

## How to deploy to a real AWS account

### 0. Prerequisites

- AWS account + IAM principal with rights to create VPC/EKS/MSK/S3/IAM
- Terraform ≥ 1.5, kubectl, helm, argocd CLI
- Container images pushed to GHCR or ECR (`ghcr.io/argus-platform/...`)

### 1. One-time remote state

```bash
aws s3 mb s3://argus-terraform-state --region us-east-1
aws s3api put-bucket-versioning --bucket argus-terraform-state \
  --versioning-configuration Status=Enabled
aws dynamodb create-table \
  --table-name argus-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

Adjust `backend "s3"` bucket/region in each `environments/*/main.tf` if needed.

### 2. Terraform apply (dev first)

**EKS API access:** the cluster public endpoint is **off** unless you pass
CIDRs. Empty `eks_public_access_cidrs` ⇒ private-only (no `0.0.0.0/0` default).

```bash
# Recommended: your current public IP as a /32 (or office/VPN egress CIDR)
MY_IP="$(curl -4 -s https://checkip.amazonaws.com)/32"
# example: 203.0.113.10/32

cd infra/terraform/environments/dev
terraform init
terraform plan \
  -var="eks_public_access_cidrs=[\"$${MY_IP}\"]" \
  -out=tfplan
# Review carefully, then ONLY if intentional:
# terraform apply tfplan
```

Or a `dev.tfvars`:

```hcl
eks_public_access_cidrs = ["203.0.113.10/32"]  # home/office/VPN — not 0.0.0.0/0
```

| Env | Recommended `eks_public_access_cidrs` |
|-----|----------------------------------------|
| **dev** | Your laptop `/32` or home ISP CIDR while bootstrapping kubectl |
| **staging** | Office or VPN egress CIDR |
| **prod** | **`[]` (default)** — private endpoint only; reach the API via VPN/bastion/SSM. Validation rejects `0.0.0.0/0`. |

Capture outputs:

```bash
terraform output cluster_name
terraform output msk_bootstrap_brokers_tls
terraform output iceberg_warehouse_uri
terraform output irsa_role_arns
```

### 3. kubeconfig + IRSA annotations

```bash
aws eks update-kubeconfig --name "$(terraform output -raw cluster_name)"
```

Patch Helm values (or External Secrets) so service accounts get:

```yaml
serviceAccount:
  annotations:
    eks.amazonaws.com/role-arn: <irsa_role_arns["lakehouse-writer"]>
```

Set `ARGUS_KAFKA_BROKERS` / MSK TLS bootstrap and `WAREHOUSE_URI` from Terraform outputs in each chart `env:`.

### 4. Install Argo CD + root app

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -f infra/argocd/root/application.yaml
```

Argo CD loads `infra/argocd/apps` and syncs each Helm chart into namespace
`argus`.

### 5. Promote

Follow [`argocd/PROMOTION.md`](./argocd/PROMOTION.md) for staging/prod.

### 6. Tear-down (cost control)

```bash
# Delete Argo apps / namespace first, then:
cd infra/terraform/environments/dev
terraform destroy
```

---

## Layout

```text
infra/
  README.md                 ← you are here
  terraform/
    modules/{networking,msk,iceberg-lakehouse,eks,iam}/
    environments/{dev,staging,prod}/main.tf
  helm/
    <service>/{Chart.yaml,values.yaml,values/,templates/}
    observability/          ← kube-prometheus-stack dependency
  argocd/
    root/application.yaml   ← app-of-apps
    apps/*.yaml             ← one Application per chart
    PROMOTION.md
```
