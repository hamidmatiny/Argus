"""Sink: fleet.scenario_ground_truth from physics world_state_3d."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from argus_pipeline.base import Sink
from argus_pipeline.registry import register
from argus_pipeline.sinks._lakehouse import append_rows, json_dumps, open_catalog


@register
class ScenarioGroundTruthSink(Sink):
    name = "scenario_ground_truth"
    inputs = ("physics",)

    def write(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        from common.catalog import ensure_table
        from common.schema import (
            SCENARIO_GROUND_TRUTH_PARTITION_SPEC,
            SCENARIO_GROUND_TRUTH_SCHEMA,
            map_scenario_ground_truth_record,
            scenario_ground_truth_rows_to_arrow,
        )

        if config.get("dry_run"):
            return {"table": "fleet.scenario_ground_truth", "rows": len(batches["physics"]), "dry_run": True}

        catalog = open_catalog(config)
        table = ensure_table(
            catalog,
            namespace=str(config.get("namespace") or "fleet"),
            table_name="scenario_ground_truth",
            schema=SCENARIO_GROUND_TRUTH_SCHEMA,
            partition_spec=SCENARIO_GROUND_TRUTH_PARTITION_SPEC,
        )
        rows = []
        for frame in batches["physics"]:
            rows.append(
                map_scenario_ground_truth_record(
                    {
                        "scenario_id": frame["scenario_id"],
                        "scenario_type": frame["scenario_type"],
                        "frame_idx": frame["frame_idx"],
                        "timestamp": frame["timestamp"],
                        "ego_vehicle_id": frame["ego_vehicle_id"],
                        "agents_json": json_dumps(frame["agents"]),
                        "world_rewards_json": json_dumps(frame["world_rewards"]),
                        "origin_lat": frame["origin"]["lat"],
                        "origin_lon": frame["origin"]["lon"],
                    }
                )
            )
        n = append_rows(table, rows, scenario_ground_truth_rows_to_arrow)
        return {"table": "fleet.scenario_ground_truth", "rows": n}
