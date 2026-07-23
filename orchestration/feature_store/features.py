"""Feature views over Dagster daily_feature_statistics Parquet."""

from datetime import timedelta
from pathlib import Path

from feast import FeatureView, Field, FileSource
from feast.types import Float32, Int64

from entities import device_type

_DATA = Path(__file__).resolve().parent / "data" / "device_feature_stats.parquet"

device_feature_stats_source = FileSource(
    name="device_feature_stats_source",
    path=str(_DATA),
    timestamp_field="computed_at",
)

device_feature_stats = FeatureView(
    name="device_feature_stats",
    entities=[device_type],
    ttl=timedelta(days=7),
    schema=[
        Field(name="row_count", dtype=Int64),
        Field(name="speed_mph_mean", dtype=Float32),
        Field(name="speed_mph_std", dtype=Float32),
        Field(name="speed_mph_p50", dtype=Float32),
        Field(name="speed_mph_p95", dtype=Float32),
        Field(name="brake_pressure_mean", dtype=Float32),
        Field(name="brake_pressure_std", dtype=Float32),
        Field(name="brake_pressure_p50", dtype=Float32),
        Field(name="brake_pressure_p95", dtype=Float32),
        Field(name="lidar_temp_c_mean", dtype=Float32),
        Field(name="lidar_temp_c_std", dtype=Float32),
        Field(name="lidar_temp_c_p50", dtype=Float32),
        Field(name="lidar_temp_c_p95", dtype=Float32),
        Field(name="compute_load_pct_mean", dtype=Float32),
        Field(name="compute_load_pct_std", dtype=Float32),
        Field(name="compute_load_pct_p50", dtype=Float32),
        Field(name="compute_load_pct_p95", dtype=Float32),
    ],
    source=device_feature_stats_source,
    online=True,
)
