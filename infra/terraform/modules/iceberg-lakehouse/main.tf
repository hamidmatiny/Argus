# Iceberg lakehouse — S3 warehouse + Glue catalog.
# Extends hydra-data-factory/terraform/main.tf patterns (bucket hardening,
# Glue database, prefix-scoped IAM) for ARGUS Iceberg on EKS via IRSA.
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

variable "environment" {
  type = string
}

variable "bucket_name" {
  type        = string
  default     = null
  description = "Optional override; default includes account id"
}

variable "glue_database_name" {
  type    = string
  default = "fleet"
}

variable "tags" {
  type    = map(string)
  default = {}
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name = coalesce(
    var.bucket_name,
    "${var.name}-iceberg-${var.environment}-${data.aws_caller_identity.current.account_id}"
  )
  # Iceberg warehouse layout (ARGUS); hydra used raw/ + analytics/.
  prefixes = ["warehouse/", "warehouse/fleet/", "quarantine/", "artifacts/"]
}

resource "aws_s3_bucket" "lakehouse" {
  bucket = local.bucket_name
  force_destroy = true
  tags = merge(var.tags, {
    Name      = local.bucket_name
    Component = "iceberg-lakehouse"
  })
}

resource "aws_s3_bucket_versioning" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lakehouse" {
  bucket = aws_s3_bucket.lakehouse.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "lakehouse" {
  bucket                  = aws_s3_bucket.lakehouse.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "prefixes" {
  for_each = toset(local.prefixes)
  bucket   = aws_s3_bucket.lakehouse.id
  key      = each.value
}

resource "aws_glue_catalog_database" "fleet" {
  name        = var.glue_database_name
  description = "ARGUS Iceberg / Glue catalog for fleet telemetry (extends hydra Glue DB pattern)."
  tags        = merge(var.tags, { Component = "iceberg-lakehouse" })
}

output "bucket_id" {
  value = aws_s3_bucket.lakehouse.id
}

output "bucket_arn" {
  value = aws_s3_bucket.lakehouse.arn
}

output "bucket_name" {
  value = aws_s3_bucket.lakehouse.bucket
}

output "glue_database_name" {
  value = aws_glue_catalog_database.fleet.name
}

output "warehouse_uri" {
  value = "s3://${aws_s3_bucket.lakehouse.bucket}/warehouse/"
}
