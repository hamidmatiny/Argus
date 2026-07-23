"""fuse_frame_transforms — align camera/lidar calibration into one per-frame bundle."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from argus_pipeline.base import Transform
from argus_pipeline.registry import register


@register
class FuseFrameTransforms(Transform):
    """Combine camera + lidar intrinsics/extrinsics keyed by matching timestamps."""

    name = "fuse_frame_transforms"
    inputs = ("camera_rendering", "lidar_rendering")

    def apply(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        lidar_by_ts = {r["timestamp"]: r for r in batches["lidar_rendering"]}
        out: list[dict[str, Any]] = []
        for cam in batches["camera_rendering"]:
            ts = cam["timestamp"]
            if ts not in lidar_by_ts:
                raise ValueError(f"camera frame timestamp {ts!r} has no lidar match")
            lid = lidar_by_ts[ts]
            out.append(
                {
                    "record_type": "calibration_bundle",
                    "scenario_id": cam["scenario_id"],
                    "frame_idx": cam["frame_idx"],
                    "timestamp": ts,
                    "ego_vehicle_id": cam["ego_vehicle_id"],
                    "camera": {
                        "intrinsics": cam["intrinsics"],
                        "extrinsics": cam["extrinsics"],
                    },
                    "lidar": {
                        "intrinsics": lid["intrinsics"],
                        "extrinsics": lid["extrinsics"],
                    },
                }
            )
        return out
