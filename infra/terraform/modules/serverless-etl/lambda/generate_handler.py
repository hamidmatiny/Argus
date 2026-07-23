"""Generate a telemetry batch via VehicleTelemetrySimulator → S3 serverless/raw/."""

from __future__ import annotations

import json
from typing import Any

import boto3

from common import require_env, resolve_execution_id, serverless_prefix
from ingestion.simulator.generator import VehicleTelemetrySimulator, default_vehicle_ids


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Write s3://{bucket}/serverless/raw/{execution_id}/batch.json."""
    execution_id = resolve_execution_id(event, context)
    batch_size = int(event.get("batch_size", 500))
    bucket = require_env("LAKEHOUSE_BUCKET")
    prefix = serverless_prefix()

    # Mild failure_rate so validate can exercise rejection_rate without always failing Choice.
    simulator = VehicleTelemetrySimulator(
        vehicle_ids=default_vehicle_ids(3),
        failure_rate=0.0,
        seed=42,
    )

    batch: list[dict[str, Any]] = []
    for index in range(batch_size):
        vehicle_id = simulator.vehicle_ids[index % len(simulator.vehicle_ids)]
        batch.append(simulator.generate_ping(vehicle_id))

    raw_key = f"{prefix}/raw/{execution_id}/batch.json"
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=raw_key,
        Body=json.dumps(batch, default=str),
        ContentType="application/json",
    )

    return {
        "raw_key": raw_key,
        "execution_id": execution_id,
        "batch_size": batch_size,
    }
