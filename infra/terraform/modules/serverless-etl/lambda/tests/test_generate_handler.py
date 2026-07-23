"""Tests for generate_handler — VehicleTelemetrySimulator → S3 raw JSON."""

from __future__ import annotations

import json

from generate_handler import lambda_handler


def test_generate_writes_valid_json_batch(aws):
    result = lambda_handler({"execution_id": "exec-gen-1", "batch_size": 12}, context=None)

    assert result["execution_id"] == "exec-gen-1"
    assert result["batch_size"] == 12
    assert result["raw_key"] == "serverless/raw/exec-gen-1/batch.json"

    body = aws["s3"].get_object(Bucket=aws["bucket"], Key=result["raw_key"])["Body"].read()
    batch = json.loads(body)

    assert isinstance(batch, list)
    assert len(batch) == 12
    required = {
        "vehicle_id",
        "trip_id",
        "timestamp",
        "gps_lat",
        "gps_lon",
        "speed_mph",
        "brake_pressure",
        "lidar_temp_c",
        "compute_load_pct",
        "sensor_status",
        "hardware_version",
        "device_type",
    }
    for row in batch:
        assert required.issubset(row.keys())
        assert row["vehicle_id"].startswith("VH-")
