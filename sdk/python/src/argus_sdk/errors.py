"""SDK errors."""

from __future__ import annotations


class ArgusError(Exception):
    """Base SDK error."""


class ArgusAuthError(ArgusError):
    """Authentication / authorization failure (401/403)."""


class ArgusAPIError(ArgusError):
    """Non-success gateway response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")
