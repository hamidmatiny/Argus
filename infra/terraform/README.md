# infra/terraform

Modules and per-environment roots for ARGUS on AWS.

| Module | Purpose |
|--------|---------|
| `networking` | VPC / subnets |
| `iceberg-lakehouse` | S3 warehouse + Glue `fleet` database |
| `eks` / `msk` / `iam` | Cluster, Kafka, IRSA |
| [`serverless-etl`](./modules/serverless-etl/) | **Demo** Lambda + Step Functions path → `fleet.serverless_batches` (not Iceberg `fleet.telemetry`) |

```bash
cd environments/dev
terraform init -backend=false
terraform validate
```

See [../README.md](../README.md) for deploy steps and remote state bootstrap.
