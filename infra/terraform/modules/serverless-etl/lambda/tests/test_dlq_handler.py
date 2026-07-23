"""Tests for dlq_handler — S3 failure object + SQS message."""

from __future__ import annotations

import json

from dlq_handler import lambda_handler


def test_dlq_writes_s3_and_sqs(aws):
    execution_id = "exec-dlq-1"
    event = {
        "execution_id": execution_id,
        "error": {"Error": "States.TaskFailed", "Cause": "boom"},
    }

    result = lambda_handler(event, context=None)

    assert result["dlq_written"] is True
    assert result["execution_id"] == execution_id
    assert result["failure_key"] == f"serverless/dead_letter/failures/{execution_id}.json"

    raw = (
        aws["s3"]
        .get_object(Bucket=aws["bucket"], Key=result["failure_key"])["Body"]
        .read()
        .decode("utf-8")
    )
    failure = json.loads(raw)
    assert failure["execution_id"] == execution_id
    assert failure["error"]["Error"] == "States.TaskFailed"
    assert "failed_at" in failure

    messages = aws["sqs"].receive_message(
        QueueUrl=aws["queue_url"],
        MaxNumberOfMessages=1,
        WaitTimeSeconds=1,
    )
    assert "Messages" in messages
    assert len(messages["Messages"]) == 1
    body = json.loads(messages["Messages"][0]["Body"])
    assert body["execution_id"] == execution_id
    assert body["error"]["Cause"] == "boom"
