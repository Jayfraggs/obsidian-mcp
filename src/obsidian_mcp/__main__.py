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
    """Run the MCP stdio server (used by Claude Desktop and all MCP clients).

    This function is preserved for backwards compatibility but the actual
    server startup is performed by `run_mcp()` which does guarded imports
    and prints clearer, actionable errors for common environments issues.
    """
    run_mcp()


def run_mcp() -> None:
    """Start the MCP stdio server. Errors are reported cleanly to stderr."""
    try:
        # Import here so `--help` or other lightweight CLI checks don't trigger heavy imports
        from obsidian_mcp.server import create_server
        from obsidian_mcp.tools.core import register_core_tools
        from obsidian_mcp.tools.knowledge import register_knowledge_tools
        from obsidian_mcp.tools.plugins import register_plugin_tools
        from obsidian_mcp.web.app import _build_system_prompt, _load_rules

        settings, vault_service, logger = _build_vault_service()

        rules = _load_rules()
        rule_count = len([
            line for line in rules.splitlines() if line.strip() and not line.startswith("#")
        ])
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

    except ModuleNotFoundError as exc:
        # Friendly message for known common cause (mcp v2 incompat)
        msg = str(exc).lower()
        if "mcp.server.fastmcp" in msg or "fastmcp" in msg:
            _print_err("[obsidian-mcp] Dependency error: incompatible 'mcp' version detected.")
            _print_err("  -> This release of obsidian-mcp expects 'mcp' v1 API (fastmcp).")
            _print_err("  -> Temporary fix: pin mcp to <2 in your environment: pip install 'mcp<2' and retry.")
        else:
            _print_err(f"[obsidian-mcp] Module not found: {exc}")
        sys.exit(1)

    except Exception as exc:
        # Print a clean error to stderr so external callers see a short, actionable message
        _print_err("\n[obsidian-mcp] STARTUP ERROR — server could not start.\n")
        _print_err(f"  {type(exc).__name__}: {exc}\n")

        # Common actionable hints
        msg = str(exc).lower()
        if "vault path" in msg or "does not exist" in msg:
            _print_err(
                "  -> Check OBSIDIAN_MCP_VAULT_PATH in your .env or claude_desktop_config.json"
            )
            _print_err("  -> Path must be absolute and must already exist")
        elif "no such file" in msg or "cannot find" in msg:
            _print_err("  -> A required file or directory was not found")
            _print_err("  -> Run: uv pip install -e . (from the obsidian-mcp project folder)")
        elif "permission" in msg or "access" in msg:
            _print_err("  -> Permission denied - check folder permissions on the vault")
        elif "adapter_api_key" in msg or "api_key" in msg:
            _print_err(
                "  -> REST API key issue - set OBSIDIAN_MCP_ADAPTER_MODE=filesystem to bypass"
            )
        elif "module" in msg or "import" in msg:
            _print_err("  -> Missing dependency - try: pip install -e . or pin 'mcp<2' if needed")

        _print_err("\nFull traceback:")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def web_main() -> None:
    """Run the local Web UI HTTP server. Validates config and displays helpful messages on error."""
    try:
        import uvicorn

        from obsidian_mcp.web.app import create_web_app

        try:
            settings, vault_service, logger = _build_vault_service()
        except Exception as exc:
            # Likely missing required settings (e.g. vault path). Print friendly help.
            _print_err(f"[obsidian-mcp-web] Configuration error: {exc}")
            _print_err("  -> Ensure OBSIDIAN_MCP_VAULT_PATH is set (environment or .env) and valid.")
            _print_err("  -> Run: python -m obsidian_mcp check to validate configuration.")
            sys.exit(1)

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
        print(f"[OK] vault_path:          {settings.vault_path}")
        print(f"[OK] adapter_mode:        {settings.adapter_mode.value}")
        print(f"[OK] permission_profile:  {settings.permission_profile.value}")
        print(f"[OK] templates_folder:    {settings.templates_folder}")
        print(f"[OK] web_port:            {settings.web_port}")
        api_key_status = "set" if settings.adapter_api_key else "not set (filesystem mode)"
        print(f"[OK] adapter_api_key:     {api_key_status}")

        from obsidian_mcp.adapters import AutoAdapter
        adapter = AutoAdapter.from_settings(settings)
        alive = adapter.health_check()
        adapter_status = "reachable" if alive else "ERROR: unreachable"
        print(f"[OK] adapter backend:     {adapter.backend_name} ({adapter_status})")

        if not alive:
            print("\n[ERROR] Vault is unreachable - check OBSIDIAN_MCP_VAULT_PATH")
            sys.exit(1)

        print("\nAll checks passed. Run with: python -m obsidian_mcp")
        sys.exit(0)

    except Exception as exc:
        print(f"\n[ERROR] Configuration error: {exc}")
        traceback.print_exc()
        sys.exit(1)


# ── CLI Dispatcher ───────────────────────────────────────────────────
def _cli() -> None:
    """Lightweight CLI that avoids heavy imports for --help and simple checks."""
    import argparse

    parser = argparse.ArgumentParser(prog="obsidian-mcp", description="Obsidian MCP server runner")
    sub = parser.add_subparsers(dest="command", help="sub-command to run")
    sub.add_parser("mcp", help="Run the MCP stdio server")
    sub.add_parser("web", help="Run the local Web UI")
    sub.add_parser("check", help="Validate configuration and exit")

    args = parser.parse_args()
    cmd = args.command or "mcp"

    if cmd == "web":
        web_main()
    elif cmd in ("check", "validate", "config"):
        check_config()
    elif cmd == "mcp":
        run_mcp()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _cli()
