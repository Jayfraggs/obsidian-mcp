"""Structured application errors for the Obsidian MCP server."""

from enum import StrEnum
from typing import TypedDict


class ErrorCode(StrEnum):
    """Stable public error codes returned by application errors."""

    CONFIGURATION_INVALID = "configuration_invalid"
    SERVER_STARTUP_FAILED = "server_startup_failed"
    VAULT_PATH_INVALID = "vault_path_invalid"
    NOTE_NOT_FOUND = "note_not_found"
    NOTE_ALREADY_EXISTS = "note_already_exists"
    VAULT_OPERATION_FAILED = "vault_operation_failed"
    PERMISSION_DENIED = "permission_denied"


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


class VaultPathError(ApplicationError):
    """Raised when a vault-relative path is invalid."""

    def __init__(self, message: str, *, internal_detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.VAULT_PATH_INVALID,
            message=message,
            internal_detail=internal_detail,
        )


class NoteNotFoundError(ApplicationError):
    """Raised when a requested note does not exist."""

    def __init__(self, message: str, *, internal_detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.NOTE_NOT_FOUND,
            message=message,
            internal_detail=internal_detail,
        )


class NoteAlreadyExistsError(ApplicationError):
    """Raised when creating or moving to an existing note path."""

    def __init__(self, message: str, *, internal_detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.NOTE_ALREADY_EXISTS,
            message=message,
            internal_detail=internal_detail,
        )


class VaultOperationError(ApplicationError):
    """Raised when a vault filesystem operation fails."""

    def __init__(self, message: str, *, internal_detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.VAULT_OPERATION_FAILED,
            message=message,
            internal_detail=internal_detail,
        )


class PermissionDeniedError(ApplicationError):
    """Raised when the active permission profile blocks an action."""

    def __init__(self, message: str, *, internal_detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.PERMISSION_DENIED,
            message=message,
            internal_detail=internal_detail,
        )
