"""fuse_rendered_data — synchronized multi-sensor record per frame."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from argus_pipeline.base import Transform
from argus_pipeline.registry import register


@register
class FuseRenderedDataTransform(Transform):
    """Join physics ground truth with camera + lidar payloads on identical timestamps."""

    name = "fuse_rendered_data"
    inputs = ("physics", "camera_rendering", "lidar_rendering")

    def apply(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        cam_by_ts = {r["timestamp"]: r for r in batches["camera_rendering"]}
        lid_by_ts = {r["timestamp"]: r for r in batches["lidar_rendering"]}
        out: list[dict[str, Any]] = []

        for phys in batches["physics"]:
            ts = phys["timestamp"]
            if ts not in cam_by_ts or ts not in lid_by_ts:
                raise ValueError(f"physics timestamp {ts!r} missing camera/lidar peer")
            cam = cam_by_ts[ts]
            lid = lid_by_ts[ts]
            out.append(
                {
                    "record_type": "synchronized_sensor_frame",
                    "scenario_id": phys["scenario_id"],
                    "scenario_type": phys["scenario_type"],
                    "frame_idx": phys["frame_idx"],
                    "timestamp": ts,
                    "ego_vehicle_id": phys["ego_vehicle_id"],
                    "camera_digest": cam["image"]["digest"],
                    "lidar_digest": lid["point_cloud"]["digest"],
                    "camera_mean_intensity": cam["image"]["mean_intensity"],
                    "lidar_n_points": lid["point_cloud"]["n_points"],
                    "agents_json": json.dumps(phys["agents"], default=str),
                    "world_rewards_json": json.dumps(phys["world_rewards"], default=str),
                    "renderer_backend": cam["renderer_backend"],
                }
            )
        return out
