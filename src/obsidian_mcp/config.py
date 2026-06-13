"""Configuration models and loading helpers for the Obsidian MCP server."""

from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from obsidian_mcp.permissions import PermissionProfile


class LogLevel(StrEnum):
    """Supported application log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AdapterMode(StrEnum):
    """Vault adapter selection strategy.

    auto        – probe REST API first, fall back to filesystem (default)
    rest        – REST API only; raise on startup if unreachable
    filesystem  – direct pathlib access only; skip REST probe
    """

    AUTO = "auto"
    REST = "rest"
    FILESYSTEM = "filesystem"


class ObsidianMCPSettings(BaseSettings):
    """Validated runtime settings for the Obsidian MCP server."""

    model_config = SettingsConfigDict(
        env_prefix="OBSIDIAN_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Core ────────────────────────────────────────────────────────────
    vault_path: Path = Field(description="Path to the Obsidian vault directory.")
    server_name: str = Field(default="obsidian-mcp", min_length=1)
    log_level: LogLevel = LogLevel.INFO
    permission_profile: PermissionProfile = PermissionProfile.SAFE_WRITE
    web_host: str = "127.0.0.1"
    web_port: int = Field(default=8765, ge=1, le=65535)

    # ── Adapter ─────────────────────────────────────────────────────────
    adapter_mode: AdapterMode = AdapterMode.AUTO
    """
    Set via OBSIDIAN_MCP_ADAPTER_MODE.
    auto | rest | filesystem
    """

    adapter_api_key: str = Field(
        default="",
        description=(
            "API key for the Obsidian Local REST API plugin. "
            "Set via OBSIDIAN_MCP_ADAPTER_API_KEY. "
            "Leave blank to use filesystem adapter."
        ),
    )
    adapter_host: str = Field(
        default="127.0.0.1",
        description="Host for the Obsidian REST API plugin (OBSIDIAN_MCP_ADAPTER_HOST).",
    )
    adapter_port: int = Field(
        default=27123,
        ge=1,
        le=65535,
        description="Port for the Obsidian REST API plugin (OBSIDIAN_MCP_ADAPTER_PORT).",
    )

    @field_validator("vault_path")
    @classmethod
    def vault_path_must_exist(cls, value: Path) -> Path:
        """Validate that the configured vault path is an existing directory."""
        if not value.exists():
            raise ValueError("Vault path does not exist.")
        if not value.is_dir():
            raise ValueError("Vault path must be a directory.")
        return value


def load_settings() -> ObsidianMCPSettings:
    """Load application settings from environment variables and `.env`."""
    return ObsidianMCPSettings()
