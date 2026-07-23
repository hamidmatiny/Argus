data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  component = "serverless-etl"
  tags = merge(var.tags, {
    Component   = local.component
    Environment = var.environment
    Path        = "demo-serverless-not-production"
  })
  # S3 keys under this prefix only — never warehouse/ (Iceberg fleet.telemetry).
  serverless_prefix = "serverless"
  glue_table_fqn    = "${var.glue_database_name}.${var.glue_table_name}"
  lambda_env = {
    LAKEHOUSE_BUCKET = var.lakehouse_bucket_id
    GLUE_DATABASE    = var.glue_database_name
    GLUE_TABLE       = var.glue_table_name
    SERVERLESS_PREFIX = local.serverless_prefix
  }
}

# Marker prefixes so the serverless layout is visible in the bucket console.
resource "aws_s3_object" "prefixes" {
  for_each = toset([
    "${local.serverless_prefix}/",
    "${local.serverless_prefix}/raw/",
    "${local.serverless_prefix}/staging/",
    "${local.serverless_prefix}/telemetry/",
    "${local.serverless_prefix}/dead_letter/",
    "${local.serverless_prefix}/dead_letter/failures/",
  ])
  bucket = var.lakehouse_bucket_id
  key    = each.value
}

# Distinct Glue table — additive in the same database; does not own fleet.telemetry.
resource "aws_glue_catalog_table" "serverless_batches" {
  name          = var.glue_table_name
  database_name = var.glue_database_name
  table_type    = "EXTERNAL_TABLE"
  description   = "ARGUS serverless ETL demo batches (NOT the Iceberg fleet.telemetry table)."

  parameters = {
    EXTERNAL              = "TRUE"
    "classification"      = "parquet"
    "projection.enabled"  = "false"
    "argus.path"          = "serverless-demo"
  }

  storage_descriptor {
    location      = "s3://${var.lakehouse_bucket_id}/${local.serverless_prefix}/telemetry/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "vehicle_id"
      type = "string"
    }
    columns {
      name = "trip_id"
      type = "string"
    }
    columns {
      name = "timestamp"
      type = "timestamp"
    }
    columns {
      name = "gps_lat"
      type = "double"
    }
    columns {
      name = "gps_lon"
      type = "double"
    }
    columns {
      name = "speed_mph"
      type = "double"
    }
    columns {
      name = "brake_pressure"
      type = "double"
    }
    columns {
      name = "lidar_temp_c"
      type = "double"
    }
    columns {
      name = "compute_load_pct"
      type = "double"
    }
    columns {
      name = "sensor_status"
      type = "string"
    }
    columns {
      name = "hardware_version"
      type = "string"
    }
    columns {
      name = "device_type"
      type = "string"
    }
  }

  partition_keys {
    name = "dt"
    type = "string"
  }
}
