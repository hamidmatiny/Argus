locals {
  lambdas = {
    generate = {
      command     = ["generate_handler.lambda_handler"]
      memory_size = 1024
      timeout     = 300
      env         = local.lambda_env
    }
    validate = {
      command     = ["validate_handler.lambda_handler"]
      memory_size = 2048
      timeout     = 300
      env         = local.lambda_env
    }
    sync = {
      command     = ["sync_handler.lambda_handler"]
      memory_size = 1024
      timeout     = 300
      env         = local.lambda_env
    }
    dlq = {
      command     = ["dlq_handler.lambda_handler"]
      memory_size = 512
      timeout     = 120
      env = merge(local.lambda_env, {
        DLQ_QUEUE_URL = aws_sqs_queue.dlq.url
      })
    }
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.lambdas
  name              = "/aws/lambda/${var.name}-serverless-etl-${each.key}"
  retention_in_days = 14
  tags              = local.tags
}

# Shared container image; entrypoint selected via image_config.command (Hydra pattern).
resource "aws_lambda_function" "generate" {
  function_name = "${var.name}-serverless-etl-generate"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  timeout       = local.lambdas["generate"].timeout
  memory_size   = local.lambdas["generate"].memory_size

  image_config {
    command = local.lambdas["generate"].command
  }

  environment {
    variables = local.lambdas["generate"].env
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
  tags       = local.tags
}

resource "aws_lambda_function" "validate" {
  function_name = "${var.name}-serverless-etl-validate"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  timeout       = local.lambdas["validate"].timeout
  memory_size   = local.lambdas["validate"].memory_size

  image_config {
    command = local.lambdas["validate"].command
  }

  environment {
    variables = local.lambdas["validate"].env
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
  tags       = local.tags
}

resource "aws_lambda_function" "sync" {
  function_name = "${var.name}-serverless-etl-sync"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  timeout       = local.lambdas["sync"].timeout
  memory_size   = local.lambdas["sync"].memory_size

  image_config {
    command = local.lambdas["sync"].command
  }

  environment {
    variables = local.lambdas["sync"].env
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
  tags       = local.tags
}

resource "aws_lambda_function" "dlq" {
  function_name = "${var.name}-serverless-etl-dlq"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  timeout       = local.lambdas["dlq"].timeout
  memory_size   = local.lambdas["dlq"].memory_size

  image_config {
    command = local.lambdas["dlq"].command
  }

  environment {
    variables = local.lambdas["dlq"].env
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
  tags       = local.tags
}
