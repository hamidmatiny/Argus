"""Corruption strategies and runtime anomaly injectors (hydra + vanguard)."""

from __future__ import annotations

import os
import random
import threading
import time
from typing import Any

# Retained for memory-leak simulation (process-local).
_MEMORY_LEAK_BUFFER: list[bytes] = []

CORRUPTION_STRATEGIES: tuple[str, ...] = (
    "drop_vehicle_id",
    "invalid_speed",
    "malformed_gps",
    "null_timestamp",
    "missing_fields",
    "corrupt_json",
)

RUNTIME_ANOMALIES: tuple[str, ...] = (
    "cpu_spike",
    "memory_leak",
)


def corrupt_payload(
    payload: dict[str, Any],
    *,
    rng: random.Random,
    vehicle_id: str,
) -> tuple[dict[str, Any] | None, str, bytes | None]:
    """
    Apply a schema/payload corruption.

    Returns:
        (maybe_dict, strategy, raw_bytes_override)
        - For most strategies: corrupted dict + strategy + None
        - For corrupt_json: (None, "corrupt_json", raw malformed bytes)
    """
    strategy = rng.choice(CORRUPTION_STRATEGIES)
    corrupted = dict(payload)

    if strategy == "drop_vehicle_id":
        corrupted.pop("vehicle_id", None)
        corrupted["vehicle_id"] = ""  # Avro still needs a string; empty is the signal
        return corrupted, strategy, None

    if strategy == "invalid_speed":
        # Out-of-contract numeric (still Avro-encodable as double).
        corrupted["speed_mph"] = 9999.0
        return corrupted, strategy, None

    if strategy == "malformed_gps":
        corrupted["gps_lat"] = 999.0
        corrupted["gps_lon"] = -999.0
        return corrupted, strategy, None

    if strategy == "null_timestamp":
        corrupted["timestamp"] = ""
        return corrupted, strategy, None

    if strategy == "missing_fields":
        corrupted["hardware_version"] = ""
        corrupted["trip_id"] = ""
        corrupted["sensor_status"] = "SENSOR_STATUS_UNSPECIFIED"
        return corrupted, strategy, None

    # corrupt_json — bypass Avro; emit raw malformed JSON bytes.
    variants = [
        (
            f'{{"vehicle_id": "{vehicle_id}", "timestamp": "2026-01-01T00:00:00Z", '
            f'"speed_mph": 62.5'
        ),  # missing closing brace
        f'{{vehicle_id: {vehicle_id}, speed_mph: NaN}}',
        '{"vehicle_id": "VH-???", "timestamp": "NOT-A-DATE", "speed_mph": "fast"}',
    ]
    raw = (rng.choice(variants) + "\n").encode("utf-8")
    return None, strategy, raw


def maybe_runtime_anomaly(
    *,
    rng: random.Random,
    failure_rate: float,
    cpu_spike_duration: float = 1.5,
    cpu_spike_threads: int = 2,
    memory_chunk_kb: int = 256,
) -> str | None:
    """
    With probability proportional to failure_rate, trigger a process anomaly.

    Returns the anomaly name if triggered, else None.
    """
    # Keep runtime anomalies rarer than schema corruptions (~30% of failure budget).
    if rng.random() >= failure_rate * 0.3:
        return None
    anomaly = rng.choice(RUNTIME_ANOMALIES)
    if anomaly == "cpu_spike":
        _trigger_cpu_spike(duration=cpu_spike_duration, threads=cpu_spike_threads)
    else:
        _trigger_memory_leak(chunk_kb=memory_chunk_kb)
    return anomaly


def _cpu_worker(stop: threading.Event) -> None:
    while not stop.is_set():
        _ = sum(i * i for i in range(8_000))


def _trigger_cpu_spike(*, duration: float, threads: int) -> None:
    stop = threading.Event()
    workers = [
        threading.Thread(target=_cpu_worker, args=(stop,), daemon=True)
        for _ in range(max(1, threads))
    ]
    for worker in workers:
        worker.start()
    time.sleep(duration)
    stop.set()
    for worker in workers:
        worker.join(timeout=1.0)


def _trigger_memory_leak(*, chunk_kb: int) -> None:
    _MEMORY_LEAK_BUFFER.append(os.urandom(max(1, chunk_kb) * 1024))


def memory_leak_bytes() -> int:
    return sum(len(chunk) for chunk in _MEMORY_LEAK_BUFFER)
