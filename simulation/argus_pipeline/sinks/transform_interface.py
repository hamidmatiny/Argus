"""transform_interface sink — per-frame camera/lidar calibration → fleet.sensor_calibration."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from argus_pipeline.base import Sink
from argus_pipeline.registry import register
from argus_pipeline.sinks._lakehouse import append_rows, json_dumps, open_catalog


@register
class TransformInterfaceSink(Sink):
    """Persist fused calibration bundles (intrinsics/extrinsics) for each frame."""

    name = "transform_interface"
    inputs = ("fuse_frame_transforms",)

    def write(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        from common.catalog import ensure_table
        from common.schema import (
            SENSOR_CALIBRATION_PARTITION_SPEC,
            SENSOR_CALIBRATION_SCHEMA,
            map_sensor_calibration_record,
            sensor_calibration_rows_to_arrow,
        )

        bundles = batches["fuse_frame_transforms"]
        if config.get("dry_run"):
            return {"table": "fleet.sensor_calibration", "rows": len(bundles), "dry_run": True}

        catalog = open_catalog(config)
        table = ensure_table(
            catalog,
            namespace=str(config.get("namespace") or "fleet"),
            table_name="sensor_calibration",
            schema=SENSOR_CALIBRATION_SCHEMA,
            partition_spec=SENSOR_CALIBRATION_PARTITION_SPEC,
        )
        rows = []
        for b in bundles:
            rows.append(
                map_sensor_calibration_record(
                    {
                        "scenario_id": b["scenario_id"],
                        "frame_idx": b["frame_idx"],
                        "timestamp": b["timestamp"],
                        "ego_vehicle_id": b["ego_vehicle_id"],
                        "camera_intrinsics_json": json_dumps(b["camera"]["intrinsics"]),
                        "camera_extrinsics_json": json_dumps(b["camera"]["extrinsics"]),
                        "lidar_intrinsics_json": json_dumps(b["lidar"]["intrinsics"]),
                        "lidar_extrinsics_json": json_dumps(b["lidar"]["extrinsics"]),
                    }
                )
            )
        n = append_rows(table, rows, sensor_calibration_rows_to_arrow)
        return {"table": "fleet.sensor_calibration", "rows": n}
