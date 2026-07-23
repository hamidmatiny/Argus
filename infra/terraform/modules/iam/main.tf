# Least-privilege IRSA roles for ARGUS workloads.
# Lakehouse writer pattern extends hydra-data-factory ETL S3/Glue IAM,
# swapped from ECS task role trust → EKS IRSA (sts:AssumeRoleWithWebIdentity).
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

variable "name" {
  type = string
}

variable "oidc_provider_arn" {
  type = string
}

variable "oidc_issuer_url" {
  type = string
}

variable "namespace" {
  type    = string
  default = "argus"
}

variable "lakehouse_bucket_arn" {
  type = string
}

variable "glue_database_name" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  oidc_host = replace(var.oidc_issuer_url, "https://", "")
  # service account name → AWS capability
  sa_roles = {
    lakehouse-writer = "lakehouse"
    orchestration    = "orchestration"
    api-gateway      = "api-gateway"
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_iam_policy_document" "irsa_assume" {
  for_each = local.sa_roles
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["system:serviceaccount:${var.namespace}:${each.key}"]
    }
  }
}

resource "aws_iam_role" "service" {
  for_each           = local.sa_roles
  name               = "${var.name}-irsa-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume[each.key].json
  tags               = merge(var.tags, { Service = each.key })
}

# --- lakehouse-writer: S3 warehouse + Glue (hydra ETL pattern, Iceberg prefixes) ---
data "aws_iam_policy_document" "lakehouse" {
  statement {
    sid       = "ListWarehouse"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.lakehouse_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["warehouse", "warehouse/*", "quarantine", "quarantine/*"]
    }
  }
  statement {
    sid    = "ReadWriteWarehouse"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "${var.lakehouse_bucket_arn}/warehouse/*",
      "${var.lakehouse_bucket_arn}/quarantine/*",
    ]
  }
  statement {
    sid    = "GlueCatalog"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchCreatePartition",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/${var.glue_database_name}",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.glue_database_name}/*",
    ]
  }
}

resource "aws_iam_policy" "lakehouse" {
  name   = "${var.name}-lakehouse-writer"
  policy = data.aws_iam_policy_document.lakehouse.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "lakehouse" {
  role       = aws_iam_role.service["lakehouse-writer"].name
  policy_arn = aws_iam_policy.lakehouse.arn
}

# --- orchestration: read artifacts + MLflow object prefix ---
data "aws_iam_policy_document" "orchestration" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      var.lakehouse_bucket_arn,
      "${var.lakehouse_bucket_arn}/artifacts/*",
    ]
  }
}

resource "aws_iam_policy" "orchestration" {
  name   = "${var.name}-orchestration"
  policy = data.aws_iam_policy_document.orchestration.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "orchestration" {
  role       = aws_iam_role.service["orchestration"].name
  policy_arn = aws_iam_policy.orchestration.arn
}

# --- api-gateway: no AWS data-plane by default (placeholder deny-all beyond assume) ---
# Role exists for future Secrets Manager / Parameter Store bindings.

output "role_arns" {
  value = { for k, r in aws_iam_role.service : k => r.arn }
}

output "lakehouse_writer_role_arn" {
  value = aws_iam_role.service["lakehouse-writer"].arn
}

output "orchestration_role_arn" {
  value = aws_iam_role.service["orchestration"].arn
}

output "api_gateway_role_arn" {
  value = aws_iam_role.service["api-gateway"].arn
}
