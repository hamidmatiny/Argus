resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-serverless-etl-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = local.tags
}
