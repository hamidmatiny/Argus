"""Node registry and DAG composition helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from argus_pipeline.base import PipelineNode, Sink, Source, Transform

T = TypeVar("T", bound=type[PipelineNode])


@dataclass
class Registry:
    sources: dict[str, type[Source]] = field(default_factory=dict)
    transforms: dict[str, type[Transform]] = field(default_factory=dict)
    sinks: dict[str, type[Sink]] = field(default_factory=dict)

    def register(self, cls: T) -> T:
        if issubclass(cls, Source) and not issubclass(cls, Transform):
            self.sources[cls.name] = cls  # type: ignore[assignment]
        elif issubclass(cls, Transform):
            self.transforms[cls.name] = cls  # type: ignore[assignment]
        elif issubclass(cls, Sink):
            self.sinks[cls.name] = cls  # type: ignore[assignment]
        else:
            raise TypeError(f"cannot register {cls!r}")
        return cls

    def get(self, name: str) -> type[PipelineNode]:
        for bucket in (self.sources, self.transforms, self.sinks):
            if name in bucket:
                return bucket[name]
        raise KeyError(f"unknown pipeline node: {name!r}")


REGISTRY = Registry()


def register(cls: T) -> T:
    """Decorator: ``@register class Foo(Source): name = 'foo'``."""
    return REGISTRY.register(cls)


@dataclass(frozen=True)
class DagEdge:
    producer: str
    consumer: str


@dataclass
class PipelineDag:
    """Ordered node names + edges derived from each node's ``inputs``."""

    nodes: list[str]
    edges: list[DagEdge]


def compose_dag(node_names: list[str]) -> PipelineDag:
    """
    Build a DAG from registered node names.

    Topological order: sources first, then transforms by dependency depth,
    then sinks. Raises on missing nodes or cycles.
    """
    nodes = list(node_names)
    for name in nodes:
        REGISTRY.get(name)

    inputs_map: dict[str, tuple[str, ...]] = {}
    for name in nodes:
        cls = REGISTRY.get(name)
        inputs_map[name] = tuple(cls.inputs)

    # Validate inputs are present in the DAG (or are implicit upstream aliases).
    for name, deps in inputs_map.items():
        for dep in deps:
            if dep not in nodes:
                raise KeyError(
                    f"node {name!r} depends on {dep!r}, which is not in the DAG"
                )

    edges = [
        DagEdge(producer=dep, consumer=name)
        for name, deps in inputs_map.items()
        for dep in deps
    ]

    # Kahn topological sort
    remaining = set(nodes)
    ordered: list[str] = []
    indegree = {n: len(inputs_map[n]) for n in nodes}
    while remaining:
        ready = sorted(n for n in remaining if indegree[n] == 0)
        if not ready:
            raise ValueError(f"cycle detected among nodes: {sorted(remaining)}")
        n = ready[0]
        ordered.append(n)
        remaining.remove(n)
        for m in remaining:
            if n in inputs_map[m]:
                indegree[m] -= 1

    return PipelineDag(nodes=ordered, edges=edges)


def ensure_builtin_nodes_loaded() -> None:
    """Import side-effect registrations for built-in sources/transforms/sinks."""
    # Local imports avoid circular deps at package import time.
    import argus_pipeline.sinks  # noqa: F401
    import argus_pipeline.sources  # noqa: F401
    import argus_pipeline.transforms  # noqa: F401
