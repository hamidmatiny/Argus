terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Remote state — create the bucket/table once (see infra/README.md).
  backend "s3" {
    bucket         = "argus-terraform-state"
    key            = "environments/prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "argus-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = local.tags
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "argus"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "eks_public_access_cidrs" {
  type        = list(string)
  description = <<-EOT
    CIDRs allowed to hit the EKS public API. Prod default is [] (public endpoint
    disabled). Prefer VPN/bastion. If you must expose the API, pass only your
    corporate VPN egress CIDR — never 0.0.0.0/0.
  EOT
  default     = []

  validation {
    condition     = !contains(var.eks_public_access_cidrs, "0.0.0.0/0")
    error_message = "prod eks_public_access_cidrs must not include 0.0.0.0/0; use a VPN/office CIDR or leave empty for private-only."
  }
}

locals {
  name = "${var.project}-${var.environment}"
  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "networking" {
  source   = "../../modules/networking"
  name     = local.name
  cidr     = "10.50.0.0/16"
  az_count = 3
  tags     = local.tags
}

module "iceberg_lakehouse" {
  source             = "../../modules/iceberg-lakehouse"
  name               = var.project
  environment        = var.environment
  glue_database_name = "fleet"
  tags               = local.tags
}

module "eks" {
  source              = "../../modules/eks"
  name                = local.name
  vpc_id              = module.networking.vpc_id
  private_subnet_ids  = module.networking.private_subnet_ids
  cluster_version     = "1.30"
  node_instance_types = ["m5.xlarge"]
  node_desired        = 3
  node_min            = 3
  node_max            = 12
  public_access_cidrs = var.eks_public_access_cidrs
  tags                = local.tags
}

module "msk" {
  source        = "../../modules/msk"
  name          = local.name
  vpc_id        = module.networking.vpc_id
  subnet_ids    = module.networking.private_subnet_ids
  broker_nodes  = 3
  instance_type = "kafka.m5.large"
  allowed_cidr  = module.networking.cidr
  tags          = local.tags
}

module "iam" {
  source               = "../../modules/iam"
  name                 = local.name
  oidc_provider_arn    = module.eks.oidc_provider_arn
  oidc_issuer_url      = module.eks.oidc_issuer_url
  namespace            = "argus"
  lakehouse_bucket_arn = module.iceberg_lakehouse.bucket_arn
  glue_database_name   = module.iceberg_lakehouse.glue_database_name
  tags                 = local.tags
}

# Parallel AWS-native demo path (Lambda/Step Functions) — not the Kafka/Iceberg writer.
module "serverless_etl" {
  source                      = "../../modules/serverless-etl"
  name                        = local.name
  environment                 = var.environment
  lakehouse_bucket_id         = module.iceberg_lakehouse.bucket_id
  lakehouse_bucket_arn        = module.iceberg_lakehouse.bucket_arn
  glue_database_name          = module.iceberg_lakehouse.glue_database_name
  enable_eventbridge_schedule = false
  tags                        = local.tags
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "msk_bootstrap_brokers_tls" {
  value = module.msk.bootstrap_brokers_tls
}

output "iceberg_warehouse_uri" {
  value = module.iceberg_lakehouse.warehouse_uri
}

output "irsa_role_arns" {
  value = module.iam.role_arns
}

output "serverless_etl_state_machine_arn" {
  value = module.serverless_etl.state_machine_arn
}

output "serverless_etl_ecr_repository_url" {
  value = module.serverless_etl.ecr_repository_url
}

output "serverless_etl_glue_table" {
  value = module.serverless_etl.glue_table_fqn
}
