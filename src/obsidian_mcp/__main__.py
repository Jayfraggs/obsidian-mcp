"""Entry point for the Obsidian MCP server.

Usage:
    python -m obsidian_mcp           → MCP stdio server (for Claude Desktop)
    python -m obsidian_mcp web       → local Web UI
    python -m obsidian_mcp check     → validate config and exit
"""

from __future__ import annotations

import sys
import traceback


def _print_err(msg: str) -> None:
    """Write to stderr — the only channel Claude Desktop reads from the process."""
    print(msg, file=sys.stderr, flush=True)


def _build_vault_service():
    """Load settings, build adapter, return (settings, vault_service)."""
    from obsidian_mcp.adapters import AutoAdapter
    from obsidian_mcp.config import load_settings
    from obsidian_mcp.logging import configure_logging, get_logger
    from obsidian_mcp.vault.service import VaultService

    settings = load_settings()
    configure_logging(settings.log_level)
    logger = get_logger("main")

    logger.info("obsidian-mcp starting | vault=%s", settings.vault_path)

    adapter = AutoAdapter.from_settings(settings)
    logger.info("Adapter: %s", adapter.backend_name)

    vault_service = VaultService(settings.vault_path, adapter=adapter)
    return settings, vault_service, logger


def main() -> None:
    """Run the MCP stdio server (used by Claude Desktop and all MCP clients)."""
    try:
        from obsidian_mcp.server import create_server
        from obsidian_mcp.tools.core import register_core_tools
        from obsidian_mcp.tools.knowledge import register_knowledge_tools
        from obsidian_mcp.tools.plugins import register_plugin_tools
        from obsidian_mcp.web.app import _build_system_prompt, _load_rules

        settings, vault_service, logger = _build_vault_service()

        rules = _load_rules()
        rule_count = len([l for l in rules.splitlines() if l.strip() and not l.startswith("#")])
        logger.info("Loaded %d vault rules.", rule_count)
        system_prompt = _build_system_prompt(rules)

        server = create_server(
            settings,
            tool_registrars=(
                register_core_tools,
                register_knowledge_tools,
                register_plugin_tools,
            ),
            vault_service=vault_service,
            system_prompt=system_prompt,
        )

        logger.info("Building backlink index and starting watcher …")
        vault_service.start()

        logger.info("MCP server ready — waiting for client.")
        try:
            server.run()  # blocks on stdio
        finally:
            vault_service.stop()

    except KeyboardInterrupt:
        _print_err("[obsidian-mcp] Stopped.")
        sys.exit(0)

    except Exception as exc:
        # Print a clean error to stderr so Claude Desktop shows it in logs
        _print_err("\n[obsidian-mcp] STARTUP ERROR — server could not start.\n")
        _print_err(f"  {type(exc).__name__}: {exc}\n")

        # Common actionable hints
        msg = str(exc).lower()
        if "vault path" in msg or "does not exist" in msg:
            _print_err("  → Check OBSIDIAN_MCP_VAULT_PATH in your .env or claude_desktop_config.json")
            _print_err("  → Path must be absolute and must already exist")
        elif "no such file" in msg or "cannot find" in msg:
            _print_err("  → A required file or directory was not found")
            _print_err("  → Run: uv pip install -e . (from the obsidian-mcp project folder)")
        elif "permission" in msg or "access" in msg:
            _print_err("  → Permission denied — check folder permissions on the vault")
        elif "adapter_api_key" in msg or "api_key" in msg:
            _print_err("  → REST API key issue — set OBSIDIAN_MCP_ADAPTER_MODE=filesystem to bypass")
        elif "module" in msg or "import" in msg:
            _print_err("  → Missing dependency — run: uv pip install -e .")

        _print_err("\nFull traceback:")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def web_main() -> None:
    """Run the local Web UI HTTP server."""
    try:
        import uvicorn
        from obsidian_mcp.web.app import create_web_app

        settings, vault_service, logger = _build_vault_service()
        logger.info("Building backlink index and starting watcher …")
        vault_service.start()
        logger.info("Web UI starting at http://%s:%s", settings.web_host, settings.web_port)

        try:
            uvicorn.run(
                create_web_app(settings, vault_service=vault_service),
                host=settings.web_host,
                port=settings.web_port,
                log_level=settings.log_level.value.lower(),
            )
        finally:
            vault_service.stop()

    except KeyboardInterrupt:
        print("\n[obsidian-mcp-web] Stopped.", flush=True)
        sys.exit(0)

    except Exception as exc:
        _print_err(f"\n[obsidian-mcp-web] ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def check_config() -> None:
    """Validate configuration and print a status report. Exits 0 on success."""
    try:
        from obsidian_mcp.config import load_settings
        settings = load_settings()
        print(f"✓ vault_path:          {settings.vault_path}")
        print(f"✓ adapter_mode:        {settings.adapter_mode.value}")
        print(f"✓ permission_profile:  {settings.permission_profile.value}")
        print(f"✓ templates_folder:    {settings.templates_folder}")
        print(f"✓ web_port:            {settings.web_port}")
        api_key_status = "set" if settings.adapter_api_key else "not set (filesystem mode)"
        print(f"✓ adapter_api_key:     {api_key_status}")

        from obsidian_mcp.adapters import AutoAdapter
        adapter = AutoAdapter.from_settings(settings)
        alive = adapter.health_check()
        print(f"✓ adapter backend:     {adapter.backend_name} ({'reachable' if alive else 'ERROR: unreachable'})")

        if not alive:
            print("\n✗ Vault is unreachable — check OBSIDIAN_MCP_VAULT_PATH")
            sys.exit(1)

        print("\nAll checks passed. Run with: python -m obsidian_mcp")
        sys.exit(0)

    except Exception as exc:
        print(f"\n✗ Configuration error: {exc}")
        traceback.print_exc()
        sys.exit(1)


# ── Dispatcher ────────────────────────────────────────────────────────
# Supports both entry-point scripts and `python -m obsidian_mcp [mode]`

if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "mcp"
    if cmd == "web":
        web_main()
    elif cmd in ("check", "validate", "config"):
        check_config()
    elif cmd == "mcp":
        main()
    else:
        _print_err(f"Unknown command: {cmd}")
        _print_err("Usage: python -m obsidian_mcp [mcp|web|check]")
        sys.exit(1)
