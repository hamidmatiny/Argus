"""Vehicle telemetry simulator with kinematic evolution (ported from hydra-data-factory)."""

from __future__ import annotations

import math
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ingestion.simulator.anomalies import corrupt_payload, maybe_runtime_anomaly

_DEFAULT_LATITUDE = 40.4406
_DEFAULT_LONGITUDE = -79.9959
_METERS_PER_DEGREE_LAT = 111_320.0

_HARDWARE_VERSIONS = ("hw-rev-3.2", "hw-rev-3.3", "hw-rev-4.0-beta")
_SENSOR_STATUSES = (
    "SENSOR_STATUS_OK",
    "SENSOR_STATUS_DEGRADED",
    "SENSOR_STATUS_FAULT",
)


@dataclass
class VehicleState:
    trip_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    latitude: float = _DEFAULT_LATITUDE
    longitude: float = _DEFAULT_LONGITUDE
    speed_mph: float = 0.0
    heading_deg: float = 0.0
    last_updated: float = field(default_factory=time.time)


class VehicleTelemetrySimulator:
    """Produces TelemetryEvent-shaped dicts, optionally corrupted for QA testing."""

    def __init__(
        self,
        vehicle_ids: list[str],
        failure_rate: float = 0.0,
        *,
        seed: int | None = None,
    ) -> None:
        if not vehicle_ids:
            raise ValueError("vehicle_ids must contain at least one identifier")
        if not 0.0 <= failure_rate <= 1.0:
            raise ValueError("failure_rate must be between 0.0 and 1.0")

        self.vehicle_ids = list(vehicle_ids)
        self.failure_rate = failure_rate
        self._rng = random.Random(seed)
        self._states: dict[str, VehicleState] = {
            vid: VehicleState(
                latitude=_DEFAULT_LATITUDE + self._rng.uniform(-0.02, 0.02),
                longitude=_DEFAULT_LONGITUDE + self._rng.uniform(-0.02, 0.02),
                speed_mph=self._rng.uniform(0.0, 35.0),
                heading_deg=self._rng.uniform(0.0, 360.0),
            )
            for vid in vehicle_ids
        }
        self.stats: dict[str, int] = {
            "emitted": 0,
            "corrupted": 0,
            "runtime_anomalies": 0,
            "corrupt_json_bytes": 0,
        }

    def generate_ping(self, vehicle_id: str) -> dict[str, Any]:
        """Generate one clean TelemetryEvent-shaped payload (no corruption)."""
        if vehicle_id not in self._states:
            raise KeyError(f"unknown vehicle_id: {vehicle_id!r}")

        state = self._states[vehicle_id]
        now = time.time()
        elapsed = max(now - state.last_updated, 0.001)
        state.last_updated = now
        self._evolve_kinematics(state, elapsed)

        compute_load = min(
            95.0, 25.0 + state.speed_mph * 0.6 + self._rng.uniform(-5.0, 10.0)
        )
        lidar_temp = 38.0 + state.speed_mph * 0.08 + self._rng.uniform(-1.5, 1.5)
        brake = max(0.0, min(1.0, state.speed_mph / 100.0 + self._rng.uniform(0.0, 0.1)))

        sensor_status = "SENSOR_STATUS_OK"
        roll = self._rng.random()
        if roll < 0.03:
            sensor_status = "SENSOR_STATUS_DEGRADED"
        elif state.speed_mph > 65.0 and roll < 0.08:
            sensor_status = "SENSOR_STATUS_FAULT"

        return {
            "vehicle_id": vehicle_id,
            "trip_id": state.trip_id,
            "timestamp": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "gps_lat": round(state.latitude, 7),
            "gps_lon": round(state.longitude, 7),
            "speed_mph": round(state.speed_mph, 2),
            "brake_pressure": round(brake, 3),
            "lidar_temp_c": round(lidar_temp, 2),
            "compute_load_pct": round(compute_load, 2),
            "sensor_status": sensor_status,
            "hardware_version": self._rng.choice(_HARDWARE_VERSIONS),
            "device_type": "DEVICE_TYPE_SIMULATOR",
        }

    def next_message(
        self, vehicle_id: str | None = None
    ) -> tuple[dict[str, Any] | None, str | None, bytes | None]:
        """
        Generate the next outbound message.

        Returns:
            (payload_dict | None, corruption_strategy | None, raw_bytes | None)
        """
        vid = vehicle_id or self._rng.choice(self.vehicle_ids)
        payload = self.generate_ping(vid)
        strategy: str | None = None
        raw: bytes | None = None

        anomaly = maybe_runtime_anomaly(rng=self._rng, failure_rate=self.failure_rate)
        if anomaly:
            self.stats["runtime_anomalies"] += 1
            payload["compute_load_pct"] = min(100.0, payload["compute_load_pct"] + 25.0)

        if self._rng.random() < self.failure_rate:
            payload, strategy, raw = corrupt_payload(
                payload, rng=self._rng, vehicle_id=vid
            )
            self.stats["corrupted"] += 1
            if raw is not None:
                self.stats["corrupt_json_bytes"] += 1

        self.stats["emitted"] += 1
        return payload, strategy, raw

    def _evolve_kinematics(self, state: VehicleState, elapsed_seconds: float) -> None:
        target = state.speed_mph + self._rng.uniform(-8.0, 8.0)
        target = max(0.0, min(target, 75.0))
        state.speed_mph += (target - state.speed_mph) * min(elapsed_seconds * 0.5, 1.0)

        if state.speed_mph < 2.0 and self._rng.random() < 0.15:
            state.heading_deg = (state.heading_deg + self._rng.uniform(-45.0, 45.0)) % 360.0

        speed_mps = state.speed_mph * 0.44704
        distance_m = speed_mps * elapsed_seconds
        heading_rad = math.radians(state.heading_deg)
        delta_lat = (distance_m * math.cos(heading_rad)) / _METERS_PER_DEGREE_LAT
        delta_lon = (distance_m * math.sin(heading_rad)) / (
            _METERS_PER_DEGREE_LAT * math.cos(math.radians(state.latitude))
        )
        state.latitude += delta_lat
        state.longitude += delta_lon


def default_vehicle_ids(n: int) -> list[str]:
    """Build VH-######## identifiers matching the shared contract regex."""
    if n < 1:
        raise ValueError("vehicles must be >= 1")
    return [f"VH-{i:07d}" for i in range(1, n + 1)]
