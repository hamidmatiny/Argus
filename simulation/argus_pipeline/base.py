"""Abstract Sources, Transforms, and Sinks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable, Iterator, Mapping, Sequence


class PipelineNode(ABC):
    """Base node with a stable registry name."""

    name: str = "unnamed"
    # Upstream node names this node consumes (empty for sources).
    inputs: Sequence[str] = ()


class Source(PipelineNode, ABC):
    """Produces a stream of records (no upstream inputs)."""

    @abstractmethod
    def generate(self, config: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield records for this source."""


class Transform(PipelineNode, ABC):
    """Maps one or more input batches into an output batch."""

    @abstractmethod
    def apply(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Return transformed records."""


class Sink(PipelineNode, ABC):
    """Persists one or more input batches; returns write metadata."""

    @abstractmethod
    def write(
        self,
        batches: Mapping[str, Sequence[dict[str, Any]]],
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Write records and return a small result dict (rows, table, …)."""


def collect(iterable: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(iterable)
