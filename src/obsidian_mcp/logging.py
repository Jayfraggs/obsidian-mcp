"""Centralized logging helpers for the Obsidian MCP server."""

import logging

from obsidian_mcp.config import LogLevel

PACKAGE_LOGGER_NAME = "obsidian_mcp"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(log_level: LogLevel) -> logging.Logger:
    """Configure and return the package logger."""
    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    logger.setLevel(log_level.value)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)

    for handler in logger.handlers:
        handler.setLevel(log_level.value)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger below the package logger."""
    return logging.getLogger(f"{PACKAGE_LOGGER_NAME}.{name}")
