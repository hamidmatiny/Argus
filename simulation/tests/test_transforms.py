"""Unit tests for transform output shapes / schemas."""

from __future__ import annotations

from argus_pipeline.runner import run_pipeline
from argus_pipeline.sources.scenario_runner import ScenarioRunnerSource
from argus_pipeline.transforms.camera_rendering import CameraRenderingTransform
from argus_pipeline.transforms.fuse_frame_transforms import FuseFrameTransforms
from argus_pipeline.transforms.fuse_rendered_data import FuseRenderedDataTransform
from argus_pipeline.transforms.lidar_rendering import LidarRenderingTransform
from argus_pipeline.transforms.physics import PhysicsTransform


def _world_batch(config: dict) -> list[dict]:
    return list(ScenarioRunnerSource().generate(config))


def test_physics_output_shape(pipeline_config):
    world = _world_batch(pipeline_config)
    frames = PhysicsTransform().apply({"scenario_runner": world}, pipeline_config)
    assert len(frames) == pipeline_config["n_frames"]
    for frame in frames:
        assert frame["record_type"] == "world_state_3d"
        assert "agents" in frame and frame["agents"]
        ego = next(a for a in frame["agents"] if a["role"] == "ego")
        assert set(ego["position"]) == {"x", "y", "z"}
        assert set(ego["orientation"]) == {"qx", "qy", "qz", "qw"}
        assert "linear_velocity_mps" in ego


def test_camera_rendering_output_shape(pipeline_config):
    world = _world_batch(pipeline_config)
    phys = PhysicsTransform().apply({"scenario_runner": world}, pipeline_config)
    cams = CameraRenderingTransform().apply({"physics": phys}, pipeline_config)
    assert len(cams) == len(phys)
    for cam in cams:
        assert cam["modality"] == "camera"
        assert cam["renderer_backend"] == "classical_proxy"
        assert cam["renderer_interface"] == "neural_renderer_shaped"
        assert {"width", "height", "digest", "mean_intensity"} <= set(cam["image"])
        assert {"fx", "fy", "cx", "cy"} <= set(cam["intrinsics"])
        assert {"tx", "ty", "tz", "yaw"} <= set(cam["extrinsics"])


def test_lidar_rendering_output_shape(pipeline_config):
    world = _world_batch(pipeline_config)
    phys = PhysicsTransform().apply({"scenario_runner": world}, pipeline_config)
    lids = LidarRenderingTransform().apply({"physics": phys}, pipeline_config)
    assert len(lids) == len(phys)
    for lid in lids:
        assert lid["modality"] == "lidar"
        assert lid["renderer_backend"] == "classical_proxy"
        assert lid["point_cloud"]["n_points"] == len(lid["point_cloud"]["returns"])
        assert lid["point_cloud"]["n_points"] > 0


def test_fuse_frame_transforms_output_shape(pipeline_config):
    world = _world_batch(pipeline_config)
    phys = PhysicsTransform().apply({"scenario_runner": world}, pipeline_config)
    cams = CameraRenderingTransform().apply({"physics": phys}, pipeline_config)
    lids = LidarRenderingTransform().apply({"physics": phys}, pipeline_config)
    fused = FuseFrameTransforms().apply(
        {"camera_rendering": cams, "lidar_rendering": lids}, pipeline_config
    )
    assert len(fused) == len(cams)
    for row in fused:
        assert row["record_type"] == "calibration_bundle"
        assert "intrinsics" in row["camera"] and "extrinsics" in row["camera"]
        assert "intrinsics" in row["lidar"] and "extrinsics" in row["lidar"]


def test_fuse_rendered_data_output_shape(pipeline_config):
    world = _world_batch(pipeline_config)
    phys = PhysicsTransform().apply({"scenario_runner": world}, pipeline_config)
    cams = CameraRenderingTransform().apply({"physics": phys}, pipeline_config)
    lids = LidarRenderingTransform().apply({"physics": phys}, pipeline_config)
    fused = FuseRenderedDataTransform().apply(
        {
            "physics": phys,
            "camera_rendering": cams,
            "lidar_rendering": lids,
        },
        pipeline_config,
    )
    assert len(fused) == len(phys)
    for row in fused:
        assert row["record_type"] == "synchronized_sensor_frame"
        assert row["camera_digest"]
        assert row["lidar_digest"]
        assert row["renderer_backend"] == "classical_proxy"
