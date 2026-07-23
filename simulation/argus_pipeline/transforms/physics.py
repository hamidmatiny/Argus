"""physics — expand world_state into full 3D poses for ego + other agents."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from argus_pipeline.base import Transform
from argus_pipeline.registry import register

_METERS_PER_DEGREE_LAT = 111_320.0


def _ll_to_local_xy(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    x = (lon - origin_lon) * _METERS_PER_DEGREE_LAT * math.cos(math.radians(origin_lat))
    y = (lat - origin_lat) * _METERS_PER_DEGREE_LAT
    return x, y


def _heading_to_quat(heading_deg: float) -> dict[str, float]:
    """Yaw-only quaternion (z-up)."""
    half = math.radians(heading_deg) * 0.5
    return {
        "qx": 0.0,
        "qy": 0.0,
        "qz": math.sin(half),
        "qw": math.cos(half),
    }


@register
class PhysicsTransform(Transform):
    name = "physics"
    inputs = ("scenario_runner",)

    def apply(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        origin_lat = float(config.get("origin_lat") or 40.4406)
        origin_lon = float(config.get("origin_lon") or -79.9959)

        for frame in batches["scenario_runner"]:
            agents_3d: list[dict[str, Any]] = []
            for agent in frame["agents"]:
                x, y = _ll_to_local_xy(
                    float(agent["gps_lat"]),
                    float(agent["gps_lon"]),
                    origin_lat,
                    origin_lon,
                )
                z = float(config.get("agent_height_m") or 1.5)
                quat = _heading_to_quat(float(agent["heading_deg"]))
                agents_3d.append(
                    {
                        **agent,
                        "position": {"x": x, "y": y, "z": z},
                        "orientation": quat,
                        "linear_velocity_mps": float(agent["speed_mph"]) * 0.44704,
                    }
                )
            out.append(
                {
                    "record_type": "world_state_3d",
                    "scenario_id": frame["scenario_id"],
                    "scenario_type": frame["scenario_type"],
                    "frame_idx": frame["frame_idx"],
                    "timestamp": frame["timestamp"],
                    "ego_vehicle_id": frame["ego_vehicle_id"],
                    "agents": agents_3d,
                    "world_rewards": frame["world_rewards"],
                    "origin": {"lat": origin_lat, "lon": origin_lon},
                }
            )
        return out
