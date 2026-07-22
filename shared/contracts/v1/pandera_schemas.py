"""Pandera DataFrameSchema contract gate for TelemetryEvent batches."""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

from v1.models import VEHICLE_ID_PATTERN

TELEMETRY_EVENT_SCHEMA = DataFrameSchema(
    {
        "vehicle_id": Column(
            str,
            checks=Check.str_matches(VEHICLE_ID_PATTERN),
            nullable=False,
        ),
        "trip_id": Column(str, checks=Check.str_length(min_value=1), nullable=False),
        "timestamp": Column(
            "datetime64[ns, UTC]",
            nullable=False,
            coerce=True,
        ),
        "gps_lat": Column(
            float,
            checks=Check.in_range(-90.0, 90.0, include_min=True, include_max=True),
            nullable=False,
            coerce=True,
        ),
        "gps_lon": Column(
            float,
            checks=Check.in_range(-180.0, 180.0, include_min=True, include_max=True),
            nullable=False,
            coerce=True,
        ),
        "speed_mph": Column(
            float,
            checks=Check.in_range(0.0, 120.0, include_min=True, include_max=True),
            nullable=False,
            coerce=True,
        ),
        "brake_pressure": Column(
            float,
            checks=Check.ge(0.0),
            nullable=False,
            coerce=True,
        ),
        "lidar_temp_c": Column(float, nullable=False, coerce=True),
        "compute_load_pct": Column(
            float,
            checks=Check.in_range(0.0, 100.0, include_min=True, include_max=True),
            nullable=False,
            coerce=True,
        ),
        "sensor_status": Column(str, nullable=False),
        "hardware_version": Column(
            str,
            checks=Check.str_length(min_value=1),
            nullable=False,
        ),
        "device_type": Column(str, nullable=False),
    },
    strict=True,
    coerce=True,
    name="TelemetryEventBatch",
)


def validate_telemetry_batch(df: pd.DataFrame) -> pd.DataFrame:
    """Validate a batch of telemetry rows; raises pandera.errors.SchemaError on failure."""
    return TELEMETRY_EVENT_SCHEMA.validate(df, lazy=True)
