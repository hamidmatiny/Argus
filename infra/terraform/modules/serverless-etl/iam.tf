# Least-privilege roles for the serverless ETL demo (style matches modules/iam).

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.name}-serverless-etl-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "lambda_exec" {
  statement {
    sid    = "ListServerlessPrefix"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
    ]
    resources = [var.lakehouse_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.serverless_prefix,
        "${local.serverless_prefix}/*",
      ]
    }
  }

  statement {
    sid    = "ReadWriteServerlessPrefix"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = ["${var.lakehouse_bucket_arn}/${local.serverless_prefix}/*"]
  }

  statement {
    sid    = "GlueServerlessTable"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:UpdateTable",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:CreatePartition",
      "glue:BatchCreatePartition",
      "glue:UpdatePartition",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/${var.glue_database_name}",
      "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.glue_database_name}/${var.glue_table_name}",
    ]
  }

  statement {
    sid       = "SqsDlqSend"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name}-serverless-etl-*",
      "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name}-serverless-etl-*:log-stream:*",
    ]
  }
}

resource "aws_iam_policy" "lambda_exec" {
  name   = "${var.name}-serverless-etl-lambda"
  policy = data.aws_iam_policy_document.lambda_exec.json
  tags   = local.tags
}

resource "aws_iam_role_policy_attachment" "lambda_exec" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_exec.arn
}

# --- Step Functions ---

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "step_functions" {
  name               = "${var.name}-serverless-etl-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "step_functions" {
  statement {
    sid    = "InvokeServerlessLambdas"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [
      aws_lambda_function.generate.arn,
      aws_lambda_function.validate.arn,
      aws_lambda_function.sync.arn,
      aws_lambda_function.dlq.arn,
    ]
  }

  statement {
    sid    = "StepFunctionsLoggingDelivery"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "StepFunctionsLogStreams"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.step_functions.arn}:*"]
  }
}

resource "aws_iam_policy" "step_functions" {
  name   = "${var.name}-serverless-etl-sfn"
  policy = data.aws_iam_policy_document.step_functions.json
  tags   = local.tags
}

resource "aws_iam_role_policy_attachment" "step_functions" {
  role       = aws_iam_role.step_functions.name
  policy_arn = aws_iam_policy.step_functions.arn
}

# --- EventBridge (only when schedule is enabled) ---

data "aws_iam_policy_document" "eventbridge_assume" {
  count = var.enable_eventbridge_schedule ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge" {
  count              = var.enable_eventbridge_schedule ? 1 : 0
  name               = "${var.name}-serverless-etl-events"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume[0].json
  tags               = local.tags
}

data "aws_iam_policy_document" "eventbridge" {
  count = var.enable_eventbridge_schedule ? 1 : 0

  statement {
    sid       = "StartServerlessEtl"
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.pipeline.arn]
  }
}

resource "aws_iam_policy" "eventbridge" {
  count  = var.enable_eventbridge_schedule ? 1 : 0
  name   = "${var.name}-serverless-etl-events"
  policy = data.aws_iam_policy_document.eventbridge[0].json
  tags   = local.tags
}

resource "aws_iam_role_policy_attachment" "eventbridge" {
  count      = var.enable_eventbridge_schedule ? 1 : 0
  role       = aws_iam_role.eventbridge[0].name
  policy_arn = aws_iam_policy.eventbridge[0].arn
}
