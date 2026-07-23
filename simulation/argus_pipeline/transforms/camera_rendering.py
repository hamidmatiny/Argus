"""camera_rendering — classical proxy renderer (NeRF-shaped interface, not neural compute)."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping, Sequence

from argus_pipeline.base import Transform
from argus_pipeline.registry import register

# Honest scoping: interface mirrors a neural renderer contract; implementation is classical.
RENDERER_BACKEND = "classical_proxy"
RENDERER_INTERFACE = "neural_renderer_shaped"


def _proxy_image_digest(scenario_id: str, frame_idx: int, ego_xy: tuple[float, float]) -> str:
    raw = f"{scenario_id}:{frame_idx}:{ego_xy[0]:.2f}:{ego_xy[1]:.2f}:camera"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@register
class CameraRenderingTransform(Transform):
    """
    Synthesize a camera payload from 3D world state.

    This is a **classical** renderer stub with the *interface shape* of a neural
    renderer (pose → sensor tensor metadata). It does **not** run NeRF / Gaussian
    splatting — see simulation/README.md.
    """

    name = "camera_rendering"
    inputs = ("physics",)

    def apply(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        width = int(config.get("camera_width") or 64)
        height = int(config.get("camera_height") or 48)
        fx = float(config.get("camera_fx") or width * 0.9)
        fy = float(config.get("camera_fy") or height * 0.9)
        out: list[dict[str, Any]] = []

        for frame in batches["physics"]:
            ego = next(a for a in frame["agents"] if a["role"] == "ego")
            pos = ego["position"]
            n_agents = len(frame["agents"])
            # Classical proxy: brightness correlates with agent density in FOV cone.
            density = min(1.0, n_agents / 5.0)
            mean_intensity = 0.35 + 0.5 * density * (1.0 / (1.0 + abs(pos["x"]) * 0.01))
            digest = _proxy_image_digest(
                frame["scenario_id"], int(frame["frame_idx"]), (pos["x"], pos["y"])
            )
            out.append(
                {
                    "record_type": "camera_frame",
                    "modality": "camera",
                    "scenario_id": frame["scenario_id"],
                    "frame_idx": frame["frame_idx"],
                    "timestamp": frame["timestamp"],
                    "ego_vehicle_id": frame["ego_vehicle_id"],
                    "renderer_backend": RENDERER_BACKEND,
                    "renderer_interface": RENDERER_INTERFACE,
                    "image": {
                        "width": width,
                        "height": height,
                        "channels": 3,
                        "encoding": "synthetic_rgb_proxy",
                        "digest": digest,
                        "mean_intensity": round(mean_intensity, 4),
                    },
                    "camera_pose": {
                        "position": pos,
                        "orientation": ego["orientation"],
                    },
                    "intrinsics": {
                        "fx": fx,
                        "fy": fy,
                        "cx": width / 2.0,
                        "cy": height / 2.0,
                    },
                    "extrinsics": {
                        "tx": 0.0,
                        "ty": 0.0,
                        "tz": 1.5,
                        "roll": 0.0,
                        "pitch": 0.0,
                        "yaw": math.degrees(
                            math.atan2(ego["orientation"]["qz"], ego["orientation"]["qw"]) * 2.0
                        ),
                    },
                }
            )
        return out
