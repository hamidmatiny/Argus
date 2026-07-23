"""Execute a composed Sources → Transforms → Sinks DAG."""

from __future__ import annotations

from typing import Any, Mapping

from argus_pipeline.base import Sink, Source, Transform, collect
from argus_pipeline.registry import (
    REGISTRY,
    compose_dag,
    ensure_builtin_nodes_loaded,
)


DEFAULT_SCENARIO_DAG = [
    "scenario_runner",
    "physics",
    "camera_rendering",
    "lidar_rendering",
    "fuse_frame_transforms",
    "fuse_rendered_data",
    "scenario_ground_truth",
    "synthetic_sensor_data",
    "transform_interface",
]


def run_pipeline(
    config: Mapping[str, Any] | None = None,
    *,
    node_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run the simulation DAG and return per-node outputs / sink metadata.

    ``config`` is passed to every node. Sink-related keys (catalog, warehouse)
    are consumed by Iceberg sinks; scenario keys by ``scenario_runner``.
    """
    ensure_builtin_nodes_loaded()
    cfg = dict(config or {})
    dag = compose_dag(node_names or list(DEFAULT_SCENARIO_DAG))

    batches: dict[str, list[dict[str, Any]]] = {}
    sink_results: dict[str, dict[str, Any]] = {}

    for name in dag.nodes:
        cls = REGISTRY.get(name)
        node = cls()
        if isinstance(node, Source):
            batches[name] = collect(node.generate(cfg))
        elif isinstance(node, Transform):
            upstream = {dep: batches[dep] for dep in node.inputs}
            batches[name] = node.apply(upstream, cfg)
        elif isinstance(node, Sink):
            upstream = {dep: batches[dep] for dep in node.inputs}
            sink_results[name] = node.write(upstream, cfg)
        else:
            raise TypeError(f"unsupported node type for {name!r}")

    return {
        "dag": [e.__dict__ for e in dag.edges],
        "node_order": dag.nodes,
        "batch_sizes": {k: len(v) for k, v in batches.items()},
        "batches": batches,
        "sinks": sink_results,
    }
