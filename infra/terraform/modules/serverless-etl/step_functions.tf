resource "aws_cloudwatch_log_group" "step_functions" {
  name              = "/aws/states/${var.name}-serverless-etl"
  retention_in_days = 14
  tags              = local.tags
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.name}-serverless-etl"
  role_arn = aws_iam_role.step_functions.arn

  definition = templatefile("${path.module}/statemachine/argus_serverless_etl.asl.json.tpl", {
    generate_arn = aws_lambda_function.generate.arn
    validate_arn = aws_lambda_function.validate.arn
    sync_arn     = aws_lambda_function.sync.arn
    dlq_arn      = aws_lambda_function.dlq.arn
    batch_size   = var.batch_size
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_functions.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tags = local.tags
}

# Cost-conscious opt-in — default false so apply does not silently start daily billing.
resource "aws_cloudwatch_event_rule" "daily" {
  count = var.enable_eventbridge_schedule ? 1 : 0

  name                = "${var.name}-serverless-etl-daily"
  description         = "Optional daily trigger for ARGUS serverless ETL demo (not production Kafka path)"
  schedule_expression = var.schedule_expression
  tags                = local.tags
}

resource "aws_cloudwatch_event_target" "daily" {
  count = var.enable_eventbridge_schedule ? 1 : 0

  rule      = aws_cloudwatch_event_rule.daily[0].name
  target_id = "ArgusServerlessEtl"
  arn       = aws_sfn_state_machine.pipeline.arn
  role_arn  = aws_iam_role.eventbridge[0].arn
}
