output "ecr_repository_url" {
  description = "Push the shared Lambda container image here before first apply of functions."
  value       = aws_ecr_repository.lambda.repository_url
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.pipeline.arn
}

output "state_machine_name" {
  value = aws_sfn_state_machine.pipeline.name
}

output "dlq_queue_url" {
  value = aws_sqs_queue.dlq.url
}

output "dlq_queue_arn" {
  value = aws_sqs_queue.dlq.arn
}

output "glue_table_name" {
  description = "Distinct Glue table (fleet.serverless_batches) — not fleet.telemetry."
  value       = aws_glue_catalog_table.serverless_batches.name
}

output "glue_table_fqn" {
  value = local.glue_table_fqn
}

output "lambda_function_arns" {
  value = {
    generate = aws_lambda_function.generate.arn
    validate = aws_lambda_function.validate.arn
    sync     = aws_lambda_function.sync.arn
    dlq      = aws_lambda_function.dlq.arn
  }
}

output "eventbridge_schedule_enabled" {
  value = var.enable_eventbridge_schedule
}
