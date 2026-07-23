# Serverless ETL demo — parallel AWS-native path (not the production Kafka/Iceberg writer).
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
  type        = string
  description = "Resource name prefix (e.g. argus-dev)."
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev / staging / prod)."
}

variable "lakehouse_bucket_id" {
  type        = string
  description = "Existing Iceberg lakehouse S3 bucket id (from iceberg-lakehouse module)."
}

variable "lakehouse_bucket_arn" {
  type        = string
  description = "Existing Iceberg lakehouse S3 bucket ARN."
}

variable "glue_database_name" {
  type        = string
  description = "Existing Glue database (e.g. fleet) — serverless table is additive."
}

variable "glue_table_name" {
  type        = string
  description = "Distinct Glue table for serverless batches (must NOT be fleet.telemetry)."
  default     = "serverless_batches"
}

variable "enable_eventbridge_schedule" {
  type        = bool
  description = "When true, EventBridge triggers the Step Functions pipeline daily (cost opt-in)."
  default     = false
}

variable "schedule_expression" {
  type        = string
  description = "EventBridge schedule when enable_eventbridge_schedule is true."
  default     = "cron(0 6 * * ? *)"
}

variable "lambda_image_tag" {
  type        = string
  description = "ECR image tag for the shared Lambda container (push separately)."
  default     = "latest"
}

variable "batch_size" {
  type        = number
  description = "Default batch size seeded into the state machine."
  default     = 500
}

variable "tags" {
  type    = map(string)
  default = {}
}
