"""Guard: SDK bundled Avro schema must match shared/avro source of truth."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / "shared" / "avro" / "telemetry_event.avsc"
BUNDLED = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "argus_sdk"
    / "data"
    / "telemetry_event.avsc"
)


def test_bundled_avsc_byte_identical_to_shared() -> None:
    assert SHARED.is_file(), f"missing {SHARED}"
    assert BUNDLED.is_file(), f"missing {BUNDLED}"
    assert BUNDLED.read_bytes() == SHARED.read_bytes(), (
        "argus_sdk/data/telemetry_event.avsc drifted from shared/avro/telemetry_event.avsc"
    )
