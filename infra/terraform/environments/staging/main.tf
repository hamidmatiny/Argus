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
    key            = "environments/staging/terraform.tfstate"
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
  default = "staging"
}

variable "eks_public_access_cidrs" {
  type        = list(string)
  description = "CIDRs for EKS public API (e.g. office/VPN). Empty = private-only."
  default     = []
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
  cidr     = "10.45.0.0/16"
  az_count = 2
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
  node_instance_types = ["t3.large"]
  node_desired        = 2
  node_min            = 1
  node_max            = 4
  public_access_cidrs = var.eks_public_access_cidrs
  tags                = local.tags
}

module "msk" {
  source        = "../../modules/msk"
  name          = local.name
  vpc_id        = module.networking.vpc_id
  subnet_ids    = module.networking.private_subnet_ids
  broker_nodes  = 2
  instance_type = "kafka.t3.small"
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
