"""Shared helpers for ARGUS serverless ETL Lambda handlers."""

from __future__ import annotations

import os
from typing import Any


def resolve_execution_id(event: dict[str, Any], context: Any) -> str:
    """Return execution_id from the event or Lambda context."""
    execution_id = event.get("execution_id")
    if execution_id:
        return str(execution_id)
    if context is not None and getattr(context, "aws_request_id", None):
        return str(context.aws_request_id)
    raise ValueError("execution_id is required and could not be resolved from context.")


def require_env(name: str) -> str:
    """Read a required environment variable."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Environment variable {name} must be set.")
    return value


def require_event_key(event: dict[str, Any], key: str) -> str:
    value = event.get(key)
    if not value:
        raise ValueError(f"Event key '{key}' is required.")
    return str(value)


def serverless_prefix() -> str:
    return os.environ.get("SERVERLESS_PREFIX", "serverless").strip() or "serverless"
