"""Configuration models and loading helpers for the Obsidian MCP server."""

from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(StrEnum):
    """Supported application log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ObsidianMCPSettings(BaseSettings):
    """Validated runtime settings for the Obsidian MCP server."""

    model_config = SettingsConfigDict(
        env_prefix="OBSIDIAN_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    vault_path: Path = Field(description="Path to the Obsidian vault directory.")
    server_name: str = Field(default="obsidian-mcp", min_length=1)
    log_level: LogLevel = LogLevel.INFO

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
