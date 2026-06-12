import logging

from obsidian_mcp.config import LogLevel
from obsidian_mcp.logging import configure_logging, get_logger


def test_configure_logging_sets_package_logger_level() -> None:
    logger = configure_logging(LogLevel.DEBUG)

    assert logger.name == "obsidian_mcp"
    assert logger.level == logging.DEBUG
    assert logger.propagate is False


def test_get_logger_returns_child_logger() -> None:
    logger = get_logger("server")

    assert logger.name == "obsidian_mcp.server"
