"""Sink: fleet.synthetic_sensor_data from fused multi-sensor frames."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from argus_pipeline.base import Sink
from argus_pipeline.registry import register
from argus_pipeline.sinks._lakehouse import append_rows, open_catalog


@register
class SyntheticSensorDataSink(Sink):
    name = "synthetic_sensor_data"
    inputs = ("fuse_rendered_data",)

    def write(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        from common.catalog import ensure_table
        from common.schema import (
            SYNTHETIC_SENSOR_PARTITION_SPEC,
            SYNTHETIC_SENSOR_SCHEMA,
            map_synthetic_sensor_record,
            synthetic_sensor_rows_to_arrow,
        )

        frames = batches["fuse_rendered_data"]
        if config.get("dry_run"):
            return {"table": "fleet.synthetic_sensor_data", "rows": len(frames), "dry_run": True}

        catalog = open_catalog(config)
        table = ensure_table(
            catalog,
            namespace=str(config.get("namespace") or "fleet"),
            table_name="synthetic_sensor_data",
            schema=SYNTHETIC_SENSOR_SCHEMA,
            partition_spec=SYNTHETIC_SENSOR_PARTITION_SPEC,
        )
        rows = [map_synthetic_sensor_record(dict(frame)) for frame in frames]
        n = append_rows(table, rows, synthetic_sensor_rows_to_arrow)
        return {"table": "fleet.synthetic_sensor_data", "rows": n}
