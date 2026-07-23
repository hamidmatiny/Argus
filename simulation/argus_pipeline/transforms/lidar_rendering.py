"""lidar_rendering — classical proxy point-cloud renderer (neural-shaped interface)."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping, Sequence

from argus_pipeline.base import Transform
from argus_pipeline.registry import register

RENDERER_BACKEND = "classical_proxy"
RENDERER_INTERFACE = "neural_renderer_shaped"


def _proxy_cloud_digest(scenario_id: str, frame_idx: int, n_points: int) -> str:
    raw = f"{scenario_id}:{frame_idx}:{n_points}:lidar"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@register
class LidarRenderingTransform(Transform):
    """
    Synthesize a lidar point-cloud *summary* from 3D world state.

    Classical range-ring proxy — not a learned neural lidar renderer.
    """

    name = "lidar_rendering"
    inputs = ("physics",)

    def apply(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        beams = int(config.get("lidar_beams") or 16)
        out: list[dict[str, Any]] = []

        for frame in batches["physics"]:
            ego = next(a for a in frame["agents"] if a["role"] == "ego")
            ego_pos = ego["position"]
            # One synthetic return per other agent + ground ring points.
            returns: list[dict[str, float]] = []
            for agent in frame["agents"]:
                if agent["role"] == "ego":
                    continue
                p = agent["position"]
                dx = p["x"] - ego_pos["x"]
                dy = p["y"] - ego_pos["y"]
                dz = p["z"] - ego_pos["z"]
                rng = math.sqrt(dx * dx + dy * dy + dz * dz)
                returns.append(
                    {
                        "range_m": round(rng, 3),
                        "azimuth_deg": round(math.degrees(math.atan2(dy, dx)), 2),
                        "elevation_deg": round(
                            math.degrees(math.atan2(dz, max(rng, 1e-3))), 2
                        ),
                        "intensity": round(max(0.05, 1.0 / (1.0 + rng * 0.05)), 3),
                    }
                )
            # Classical ground ring
            for i in range(beams):
                az = (360.0 / beams) * i
                returns.append(
                    {
                        "range_m": 20.0,
                        "azimuth_deg": az,
                        "elevation_deg": -5.0,
                        "intensity": 0.2,
                    }
                )

            n_points = len(returns)
            digest = _proxy_cloud_digest(
                frame["scenario_id"], int(frame["frame_idx"]), n_points
            )
            out.append(
                {
                    "record_type": "lidar_frame",
                    "modality": "lidar",
                    "scenario_id": frame["scenario_id"],
                    "frame_idx": frame["frame_idx"],
                    "timestamp": frame["timestamp"],
                    "ego_vehicle_id": frame["ego_vehicle_id"],
                    "renderer_backend": RENDERER_BACKEND,
                    "renderer_interface": RENDERER_INTERFACE,
                    "point_cloud": {
                        "n_points": n_points,
                        "encoding": "synthetic_range_returns_proxy",
                        "digest": digest,
                        "returns": returns,
                    },
                    "lidar_pose": {
                        "position": ego_pos,
                        "orientation": ego["orientation"],
                    },
                    "intrinsics": {
                        "beams": beams,
                        "max_range_m": float(config.get("lidar_max_range_m") or 80.0),
                    },
                    "extrinsics": {
                        "tx": 0.0,
                        "ty": 0.0,
                        "tz": 1.8,
                        "roll": 0.0,
                        "pitch": 0.0,
                        "yaw": 0.0,
                    },
                }
            )
        return out
