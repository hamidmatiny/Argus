"""Schema drift guardrails: Pydantic, Pandera, Avro, and generated protobuf stay aligned."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "shared" / "proto"
AVRO_PATH = ROOT / "shared" / "avro" / "telemetry_event.avsc"
GEN_PYTHON = ROOT / "shared" / "gen" / "python"

sys.path.insert(0, str(CONTRACTS_DIR))
sys.path.insert(0, str(GEN_PYTHON))

from v1.models import (  # noqa: E402
    DeviceType,
    IncidentEvent,
    IncidentSeverity,
    IncidentStatus,
    SensorStatus,
    TelemetryEvent,
)
from v1.pandera_schemas import TELEMETRY_EVENT_SCHEMA, validate_telemetry_batch  # noqa: E402

TELEMETRY_FIELDS = (
    "vehicle_id",
    "trip_id",
    "timestamp",
    "gps_lat",
    "gps_lon",
    "speed_mph",
    "brake_pressure",
    "lidar_temp_c",
    "compute_load_pct",
    "sensor_status",
    "hardware_version",
    "device_type",
)

INCIDENT_FIELDS = (
    "incident_id",
    "severity",
    "source_service",
    "metric_name",
    "threshold",
    "observed_value",
    "timestamp",
    "status",
)


def _pydantic_fields(model: type) -> list[str]:
    return list(model.model_fields.keys())


def _pandera_fields() -> list[str]:
    return list(TELEMETRY_EVENT_SCHEMA.columns.keys())


def _avro_fields() -> list[str]:
    schema = json.loads(AVRO_PATH.read_text())
    return [field["name"] for field in schema["fields"]]


def _proto_message_fields(proto_path: Path, message_name: str) -> list[str]:
    """Parse field names from a proto3 message body (order-preserving)."""
    text = proto_path.read_text()
    match = re.search(
        rf"message\s+{re.escape(message_name)}\s*\{{(.*?)\n\}}",
        text,
        re.DOTALL,
    )
    assert match, f"message {message_name} not found in {proto_path}"
    body = match.group(1)
    fields: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        # type name = N;
        m = re.match(r"^[A-Za-z_][\w.]*\s+([A-Za-z_]\w*)\s*=\s*\d+\s*;", line)
        if m:
            fields.append(m.group(1))
    return fields


def _generated_pb_fields(message_cls: type) -> list[str]:
    return [f.name for f in message_cls.DESCRIPTOR.fields]


@pytest.fixture(scope="module")
def telemetry_pb():
    try:
        from argus.v1 import telemetry_pb2
    except ImportError as exc:  # pragma: no cover
        pytest.fail(
            f"generated protobuf missing ({exc}); run `make proto` first"
        )
    return telemetry_pb2


@pytest.fixture(scope="module")
def incident_pb():
    try:
        from argus.v1 import incident_pb2
    except ImportError as exc:  # pragma: no cover
        pytest.fail(
            f"generated protobuf missing ({exc}); run `make proto` first"
        )
    return incident_pb2


def test_telemetry_field_names_match_across_formats(telemetry_pb):
    pydantic_names = _pydantic_fields(TelemetryEvent)
    pandera_names = _pandera_fields()
    avro_names = _avro_fields()
    proto_names = _proto_message_fields(
        PROTO_DIR / "argus" / "v1" / "telemetry.proto", "TelemetryEvent"
    )
    generated_names = _generated_pb_fields(telemetry_pb.TelemetryEvent)

    assert pydantic_names == list(TELEMETRY_FIELDS)
    assert pandera_names == list(TELEMETRY_FIELDS)
    assert avro_names == list(TELEMETRY_FIELDS)
    assert proto_names == list(TELEMETRY_FIELDS)
    assert generated_names == list(TELEMETRY_FIELDS)


def test_incident_field_names_match_proto_and_pydantic(incident_pb):
    pydantic_names = _pydantic_fields(IncidentEvent)
    proto_names = _proto_message_fields(
        PROTO_DIR / "argus" / "v1" / "incident.proto", "IncidentEvent"
    )
    generated_names = _generated_pb_fields(incident_pb.IncidentEvent)

    assert pydantic_names == list(INCIDENT_FIELDS)
    assert proto_names == list(INCIDENT_FIELDS)
    assert generated_names == list(INCIDENT_FIELDS)


def test_avro_schema_parses_and_roundtrips():
    import fastavro

    schema = json.loads(AVRO_PATH.read_text())
    parsed = fastavro.parse_schema(schema)

    record = {
        "vehicle_id": "VH-0001234",
        "trip_id": "trip-abc",
        "timestamp": "2026-07-22T12:00:00Z",
        "gps_lat": 37.77,
        "gps_lon": -122.42,
        "speed_mph": 42.5,
        "brake_pressure": 0.1,
        "lidar_temp_c": 31.2,
        "compute_load_pct": 55.0,
        "sensor_status": "SENSOR_STATUS_OK",
        "hardware_version": "hw-rev-3.2",
        "device_type": "DEVICE_TYPE_VEHICLE",
    }
    import io

    buf = io.BytesIO()
    fastavro.schemaless_writer(buf, parsed, record)
    buf.seek(0)
    decoded = fastavro.schemaless_reader(buf, parsed)
    assert decoded["vehicle_id"] == record["vehicle_id"]
    assert decoded["speed_mph"] == record["speed_mph"]
    assert set(decoded.keys()) == set(TELEMETRY_FIELDS)


def test_pydantic_accepts_valid_telemetry():
    event = TelemetryEvent(
        vehicle_id="VH-0001234",
        trip_id="trip-1",
        timestamp="2026-07-22T15:00:00+00:00",
        gps_lat=37.7749,
        gps_lon=-122.4194,
        speed_mph=55.0,
        brake_pressure=0.2,
        lidar_temp_c=28.0,
        compute_load_pct=40.0,
        sensor_status=SensorStatus.OK,
        hardware_version="hw-rev-3.2",
        device_type=DeviceType.VEHICLE,
    )
    assert event.vehicle_id == "VH-0001234"
    assert event.timestamp.tzinfo is not None


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"speed_mph": 121.0}, "speed_mph"),
        ({"gps_lat": 91.0}, "gps_lat"),
        ({"gps_lon": -181.0}, "gps_lon"),
        ({"vehicle_id": "BAD"}, "vehicle_id"),
        ({"timestamp": ""}, "timestamp"),
    ],
)
def test_pydantic_rejects_invalid_telemetry(overrides: dict, match: str):
    payload = {
        "vehicle_id": "VH-0001234",
        "trip_id": "trip-1",
        "timestamp": "2026-07-22T15:00:00Z",
        "gps_lat": 10.0,
        "gps_lon": 20.0,
        "speed_mph": 30.0,
        "brake_pressure": 0.0,
        "lidar_temp_c": 25.0,
        "compute_load_pct": 10.0,
        "sensor_status": SensorStatus.OK,
        "hardware_version": "hw-1",
        "device_type": DeviceType.VEHICLE,
    }
    payload.update(overrides)
    with pytest.raises(ValidationError) as exc:
        TelemetryEvent.model_validate(payload)
    assert match in str(exc.value)


def test_pandera_accepts_valid_batch():
    df = pd.DataFrame(
        [
            {
                "vehicle_id": "VH-0001",
                "trip_id": "t1",
                "timestamp": datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
                "gps_lat": 0.0,
                "gps_lon": 0.0,
                "speed_mph": 0.0,
                "brake_pressure": 0.0,
                "lidar_temp_c": 20.0,
                "compute_load_pct": 0.0,
                "sensor_status": "SENSOR_STATUS_OK",
                "hardware_version": "hw-1",
                "device_type": "DEVICE_TYPE_VEHICLE",
            },
            {
                "vehicle_id": "VH-99999999",
                "trip_id": "t2",
                "timestamp": "2026-07-22T13:00:00Z",
                "gps_lat": 90.0,
                "gps_lon": 180.0,
                "speed_mph": 120.0,
                "brake_pressure": 1.0,
                "lidar_temp_c": 40.0,
                "compute_load_pct": 100.0,
                "sensor_status": "SENSOR_STATUS_DEGRADED",
                "hardware_version": "hw-2",
                "device_type": "DEVICE_TYPE_EDGE_GATEWAY",
            },
        ]
    )
    validated = validate_telemetry_batch(df)
    assert len(validated) == 2


def test_pandera_rejects_speed_and_bad_vehicle_id():
    df = pd.DataFrame(
        [
            {
                "vehicle_id": "NOPE",
                "trip_id": "t1",
                "timestamp": datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
                "gps_lat": 0.0,
                "gps_lon": 0.0,
                "speed_mph": 200.0,
                "brake_pressure": 0.0,
                "lidar_temp_c": 20.0,
                "compute_load_pct": 0.0,
                "sensor_status": "SENSOR_STATUS_OK",
                "hardware_version": "hw-1",
                "device_type": "DEVICE_TYPE_VEHICLE",
            }
        ]
    )
    with pytest.raises(Exception) as exc:
        validate_telemetry_batch(df)
    message = str(exc.value).lower()
    assert "vehicle_id" in message or "speed_mph" in message


def test_incident_pydantic_roundtrip():
    event = IncidentEvent(
        incident_id="inc-1",
        severity=IncidentSeverity.CRITICAL,
        source_service="drift-monitor",
        metric_name="speed_mph_psi",
        threshold=0.2,
        observed_value=0.55,
        timestamp="2026-07-22T16:00:00Z",
        status=IncidentStatus.OPEN,
    )
    assert event.source_service == "drift-monitor"


def test_generated_proto_roundtrip(telemetry_pb):
    msg = telemetry_pb.TelemetryEvent(
        vehicle_id="VH-0001234",
        trip_id="trip-1",
        timestamp="2026-07-22T15:00:00Z",
        gps_lat=1.0,
        gps_lon=2.0,
        speed_mph=10.0,
        brake_pressure=0.5,
        lidar_temp_c=22.0,
        compute_load_pct=33.0,
        sensor_status=telemetry_pb.SENSOR_STATUS_OK,
        hardware_version="hw-rev-3.2",
        device_type=telemetry_pb.DEVICE_TYPE_VEHICLE,
    )
    parsed = telemetry_pb.TelemetryEvent()
    parsed.ParseFromString(msg.SerializeToString())
    assert parsed.vehicle_id == "VH-0001234"
    assert parsed.sensor_status == telemetry_pb.SENSOR_STATUS_OK
