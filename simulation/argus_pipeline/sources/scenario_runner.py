"""scenario_runner — scripted/randomized driving scenarios on VehicleTelemetrySimulator kinematics."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping

from ingestion.simulator.generator import VehicleTelemetrySimulator, default_vehicle_ids

from argus_pipeline.base import Source
from argus_pipeline.registry import register

SCENARIO_TYPES = (
    "intersection",
    "highway_merge",
    "pedestrian_crossing",
    "hard_brake",
)


def _scenario_script(
    scenario_type: str,
    frame_idx: int,
    n_frames: int,
    drift_signature: Mapping[str, float] | None,
) -> dict[str, float]:
    """Return kinematic overrides + reward terms for this frame."""
    t = frame_idx / max(n_frames - 1, 1)
    brake = 0.1
    speed_bias = 0.0
    reward_collision = 0.0
    reward_comfort = 1.0 - abs(0.5 - t)

    if scenario_type == "hard_brake":
        # Peak brake mid-scenario; amplify if drift signature highlights brake_pressure.
        amp = 1.0 + float((drift_signature or {}).get("brake_pressure", 0.0))
        brake = min(1.0, 0.15 + amp * (0.85 if 0.35 <= t <= 0.55 else 0.1))
        speed_bias = -25.0 if 0.35 <= t <= 0.7 else 0.0
        reward_comfort = max(0.0, 1.0 - brake)
    elif scenario_type == "highway_merge":
        amp = 1.0 + float((drift_signature or {}).get("speed_mph", 0.0))
        speed_bias = 15.0 * amp * math.sin(math.pi * t)
        brake = 0.05
    elif scenario_type == "pedestrian_crossing":
        brake = 0.6 if 0.4 <= t <= 0.55 else 0.1
        speed_bias = -10.0 if 0.4 <= t <= 0.6 else 5.0
        reward_collision = 0.2 if 0.45 <= t <= 0.5 else 0.0
    elif scenario_type == "intersection":
        speed_bias = -8.0 if t < 0.3 else (12.0 if t > 0.6 else 0.0)
        brake = 0.4 if 0.25 <= t <= 0.4 else 0.08

    return {
        "brake_pressure": brake,
        "speed_bias_mph": speed_bias,
        "reward_collision_risk": reward_collision,
        "reward_comfort": reward_comfort,
        "reward_progress": t,
    }


@register
class ScenarioRunnerSource(Source):
    """
    Emit ``world_state`` + ``world_rewards`` frames for a named driving scenario.

    Extends ``VehicleTelemetrySimulator`` kinematics rather than reimplementing them.
    """

    name = "scenario_runner"
    inputs = ()

    def generate(self, config: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        scenario_type = str(config.get("scenario_type") or "hard_brake")
        if scenario_type not in SCENARIO_TYPES:
            raise ValueError(
                f"unknown scenario_type {scenario_type!r}; expected one of {SCENARIO_TYPES}"
            )
        n_frames = int(config.get("n_frames") or 20)
        seed = config.get("seed")
        drift_signature = config.get("drift_signature") or {}
        scenario_id = str(config.get("scenario_id") or f"scn-{uuid.uuid4().hex[:10]}")
        ego_id = str(config.get("ego_vehicle_id") or default_vehicle_ids(1)[0])
        other_ids = list(config.get("other_vehicle_ids") or default_vehicle_ids(3)[1:])

        sim = VehicleTelemetrySimulator(
            vehicle_ids=[ego_id, *other_ids],
            failure_rate=0.0,
            seed=int(seed) if seed is not None else 7,
        )

        for frame_idx in range(n_frames):
            script = _scenario_script(scenario_type, frame_idx, n_frames, drift_signature)
            agents: list[dict[str, Any]] = []
            for vid in sim.vehicle_ids:
                ping = sim.generate_ping(vid)
                # Apply scenario overlays on top of kinematic ping.
                speed = max(0.0, min(120.0, float(ping["speed_mph"]) + script["speed_bias_mph"]))
                brake = (
                    float(script["brake_pressure"])
                    if vid == ego_id
                    else float(ping["brake_pressure"])
                )
                agents.append(
                    {
                        "agent_id": vid,
                        "role": "ego" if vid == ego_id else "other",
                        "vehicle_id": vid,
                        "trip_id": ping["trip_id"],
                        "gps_lat": ping["gps_lat"],
                        "gps_lon": ping["gps_lon"],
                        "speed_mph": speed,
                        "brake_pressure": brake,
                        "heading_deg": sim._states[vid].heading_deg,
                        "sensor_status": ping["sensor_status"],
                        "hardware_version": ping["hardware_version"],
                        "device_type": ping["device_type"],
                    }
                )

            ts = datetime.now(timezone.utc).isoformat()
            # Stable per-frame timestamps when configured (tests / reproducibility).
            if config.get("base_timestamp"):
                base = datetime.fromisoformat(
                    str(config["base_timestamp"]).replace("Z", "+00:00")
                )
                from datetime import timedelta

                ts = (base + timedelta(milliseconds=100 * frame_idx)).isoformat()

            yield {
                "record_type": "world_state",
                "scenario_id": scenario_id,
                "scenario_type": scenario_type,
                "frame_idx": frame_idx,
                "timestamp": ts,
                "ego_vehicle_id": ego_id,
                "agents": agents,
                "world_rewards": {
                    "collision_risk": script["reward_collision_risk"],
                    "comfort": script["reward_comfort"],
                    "progress": script["reward_progress"],
                },
                "drift_signature": dict(drift_signature),
            }
