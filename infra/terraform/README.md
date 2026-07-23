# infra/terraform

Modules and per-environment roots for ARGUS on AWS.

```bash
cd environments/dev
terraform init -backend=false
terraform validate
```

See [../README.md](../README.md) for deploy steps and remote state bootstrap.
