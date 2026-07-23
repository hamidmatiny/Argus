"""ARGUS Python SDK — typed client for the api-gateway and Kafka ingest."""

from __future__ import annotations

from argus_sdk.client import ArgusClient
from argus_sdk.errors import ArgusAPIError, ArgusAuthError, ArgusError
from argus_sdk.ingest import IngestClient
from argus_sdk.models import (
    DeviceType,
    IncidentSummary,
    RetrainResponse,
    SensorStatus,
    TelemetryEvent,
    TelemetryQueryResult,
)

__all__ = [
    "ArgusAPIError",
    "ArgusAuthError",
    "ArgusClient",
    "ArgusError",
    "DeviceType",
    "IncidentSummary",
    "IngestClient",
    "RetrainResponse",
    "SensorStatus",
    "TelemetryEvent",
    "TelemetryQueryResult",
]

__version__ = "0.1.0"
