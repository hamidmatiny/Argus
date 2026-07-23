"""Integration: full scenario DAG produces synchronized camera/lidar timestamps."""

from __future__ import annotations

from argus_pipeline.runner import run_pipeline


def test_full_scenario_produces_synchronized_sensor_records(pipeline_config):
    result = run_pipeline(pipeline_config)
    n = pipeline_config["n_frames"]

    assert result["batch_sizes"]["scenario_runner"] == n
    assert result["batch_sizes"]["physics"] == n
    assert result["batch_sizes"]["camera_rendering"] == n
    assert result["batch_sizes"]["lidar_rendering"] == n
    assert result["batch_sizes"]["fuse_rendered_data"] == n
    assert result["batch_sizes"]["fuse_frame_transforms"] == n

    cams = result["batches"]["camera_rendering"]
    lids = result["batches"]["lidar_rendering"]
    fused = result["batches"]["fuse_rendered_data"]

    cam_ts = [c["timestamp"] for c in cams]
    lid_ts = [l["timestamp"] for l in lids]
    fused_ts = [f["timestamp"] for f in fused]

    assert cam_ts == lid_ts == fused_ts
    assert len(set(cam_ts)) == n  # unique per frame

    assert result["sinks"]["scenario_ground_truth"]["rows"] == n
    assert result["sinks"]["synthetic_sensor_data"]["rows"] == n
    assert result["sinks"]["transform_interface"]["rows"] == n
    assert result["sinks"]["scenario_ground_truth"]["table"] == "fleet.scenario_ground_truth"
    assert result["sinks"]["synthetic_sensor_data"]["table"] == "fleet.synthetic_sensor_data"
