"""Structured application errors for the Obsidian MCP server."""

from enum import StrEnum
from typing import TypedDict


class ErrorCode(StrEnum):
    """Stable public error codes returned by application errors."""

    CONFIGURATION_INVALID = "configuration_invalid"
    SERVER_STARTUP_FAILED = "server_startup_failed"


class PublicErrorPayload(TypedDict):
    """Safe error payload that can be returned to clients."""

    code: str
    message: str


class ApplicationError(Exception):
    """Base application error with a safe public representation."""

    def __init__(
        self,
        *,
        code: ErrorCode,
        message: str,
        internal_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.internal_detail = internal_detail

    def to_public_dict(self) -> PublicErrorPayload:
        """Return a client-safe error payload without internal details."""
        return {
            "code": self.code.value,
            "message": self.message,
        }


class ConfigurationError(ApplicationError):
    """Raised when application configuration is invalid."""

    def __init__(self, message: str, *, internal_detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.CONFIGURATION_INVALID,
            message=message,
            internal_detail=internal_detail,
        )
