"""Feast entities for ARGUS device-level features."""

from feast import Entity

device_type = Entity(
    name="device_type",
    join_keys=["device_type"],
    description="Fleet device_type enum (e.g. DEVICE_TYPE_SIMULATOR)",
)
