# MSK (managed Kafka) — production replacement for local Redpanda.
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

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "kafka_version" {
  type    = string
  default = "3.6.0"
}

variable "broker_nodes" {
  type    = number
  default = 2
}

variable "instance_type" {
  type    = string
  default = "kafka.t3.small"
}

variable "allowed_cidr" {
  type        = string
  description = "CIDR allowed to reach MSK brokers (typically VPC CIDR)"
}

variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_security_group" "msk" {
  name        = "${var.name}-msk"
  description = "MSK brokers"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 9092
    to_port     = 9098
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
    description = "Kafka plaintext/TLS/SASL within VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name}-msk-sg" })
}

resource "aws_cloudwatch_log_group" "msk" {
  name              = "/argus/${var.name}/msk"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_msk_configuration" "this" {
  name              = "${var.name}-msk-cfg"
  kafka_versions    = [var.kafka_version]
  server_properties = <<-EOT
    auto.create.topics.enable=true
    default.replication.factor=${min(var.broker_nodes, 3)}
    min.insync.replicas=1
    num.partitions=6
  EOT
}

resource "aws_msk_cluster" "this" {
  cluster_name           = "${var.name}-msk"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = var.broker_nodes

  broker_node_group_info {
    instance_type   = var.instance_type
    client_subnets  = var.subnet_ids
    security_groups = [aws_security_group.msk.id]
    storage_info {
      ebs_storage_info {
        volume_size = 50
      }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.this.arn
    revision = aws_msk_configuration.this.latest_revision
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk.name
      }
    }
  }

  tags = var.tags
}

output "bootstrap_brokers_tls" {
  value = aws_msk_cluster.this.bootstrap_brokers_tls
}

output "cluster_arn" {
  value = aws_msk_cluster.this.arn
}

output "security_group_id" {
  value = aws_security_group.msk.id
}
