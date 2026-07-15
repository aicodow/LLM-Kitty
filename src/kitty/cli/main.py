"""
CLI entry point — Typer-based command-line interface for the Kitty LLM framework.

Usage:
    kitty eval run -c kittyconfig.yaml
    kitty eval list
    kitty redteam run -c kittyconfig.yaml
    kitty plugins list
    kitty plugins show hateful
    kitty providers test openai:chat:gpt-4.1
    kitty providers list
    kitty server --port 15500
    kitty cache stats
    kitty db migrate
    kitty init --example
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import typer
from rich.console import Console
from rich.table import Table

from kitty.cache import CacheManager
from kitty.config import load_config
from kitty.db import get_evaluations
from kitty.pipeline import EvalPipeline
from kitty.plugins import discover_plugins, get_plugin_manifest
from kitty.providers.registry import Registry

# ---------------------------------------------------------------------------
# Top-level application
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="kitty", help="Kitty — LLM red teaming & evaluation framework", no_args_is_help=True
)

eval_app = typer.Typer(help="Run and manage evaluations", no_args_is_help=True)
redteam_app = typer.Typer(help="Red teaming operations", no_args_is_help=True)
plugins_app = typer.Typer(help="List and inspect plugins", no_args_is_help=True)
providers_app = typer.Typer(help="Test and list providers", no_args_is_help=True)

app.add_typer(eval_app, name="eval")
app.add_typer(redteam_app, name="redteam")
app.add_typer(plugins_app, name="plugins")
app.add_typer(providers_app, name="providers")


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Kitty — LLM red teaming & evaluation framework."""
    if verbose:
        os.environ["LOG_LEVEL"] = "debug"
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        logging.getLogger("kitty").setLevel(logging.DEBUG)


# ===================================================================
#  eval commands
# ===================================================================


@eval_app.command("run")
def eval_run(
    config: str = typer.Option("kittyconfig.yaml", "--config", "-c", help="Path to config file"),
    output: str | None = typer.Option(None, "--output", "-o", help="Export path for results JSON"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable response cache"),
    max_concurrency: int | None = typer.Option(
        None, "--max-concurrency", help="Override max concurrency"
    ),
    resume: bool = typer.Option(False, "--resume", help="Resume a previous evaluation"),
    retry_errors: bool = typer.Option(False, "--retry-errors", help="Retry failed test cases"),
) -> None:
    """Run an evaluation from a YAML configuration file."""

    async def _run() -> dict:
        if no_cache:
            os.environ["KITTY_DISABLE_CACHE"] = "1"
        cfg = load_config(config)
        pipeline = EvalPipeline(cfg, max_concurrency=max_concurrency)
        result = await pipeline.run(resume=resume, retry_errors=retry_errors)
        return result

    result = asyncio.run(_run())
    stats = result.get("stats", {})

    total = stats.get("totalTests", 0)
    passed = stats.get("totalPassed", 0)
    failed = stats.get("totalFailed", 0)
    errors = stats.get("totalErrors", 0)
    rate = stats.get("passRate")

    typer.echo(f"Results: {total} tests | {passed} passed | {failed} failed | {errors} errors")
    if rate is not None:
        typer.echo(f"Pass rate: {rate:.1%}")
    else:
        typer.echo("Pass rate: N/A")

    if output:
        out_path = os.path.abspath(output)
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        typer.echo(f"Results exported to {out_path}")


@eval_app.command("list")
def eval_list(
    limit: int = typer.Option(20, "--limit", help="Maximum number of evaluations to show"),
) -> None:
    """List recent evaluations from the database."""

    async def _list() -> list:
        return await get_evaluations(limit=limit)

    items = asyncio.run(_list())

    table = Table(title=f"Recent Evaluations (up to {limit})")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Created", style="green")
    table.add_column("Status", style="magenta")
    table.add_column("Tests", justify="right")
    table.add_column("Pass Rate", justify="right")

    for ev in items:
        ev_id = ev.get("id", "")[:8] if ev.get("id") else ""
        desc = (ev.get("description") or "")[:60]
        created = str(ev.get("createdAt") or "")[:19]
        status = ev.get("status", "")
        tests = str(ev.get("totalTests", 0))
        rate = ev.get("passRate")
        rate_str = f"{rate:.0%}" if rate is not None else "N/A"

        table.add_row(ev_id, desc, created, status, tests, rate_str)

    Console().print(table)


# ===================================================================
#  redteam commands
# ===================================================================


@redteam_app.command("run")
def redteam_run(
    config: str = typer.Option("kittyconfig.yaml", "--config", "-c", help="Path to config file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Generate tests without executing"),
) -> None:
    """Run a red teaming evaluation to probe for vulnerabilities."""

    async def _run() -> dict:
        cfg = load_config(config)
        if not cfg.get("redteam"):
            typer.echo("Error: No redteam section found in configuration.", err=True)
            raise typer.Exit(code=1)

        from kitty.plugins import PluginEngine

        engine = PluginEngine(cfg)

        if dry_run:
            typer.echo("Dry-run mode: generating test cases without executing ...")
            tests = await engine.generate_tests(dry_run=True)
            return {"tests": tests, "dry_run": True}

        pipeline = EvalPipeline(cfg)
        result = await pipeline.run()
        return result

    result = asyncio.run(_run())

    if dry_run:
        tests = result.get("tests", [])
        table = Table(title=f"Generated Red Team Tests ({len(tests)} total)")
        table.add_column("#", style="dim")
        table.add_column("Plugin", style="cyan")
        table.add_column("Prompt Preview")
        for i, t in enumerate(tests[:20], 1):
            table.add_row(str(i), t.get("pluginId", ""), str(t.get("prompt", ""))[:80])
        Console().print(table)
        if len(tests) > 20:
            typer.echo(f"... and {len(tests) - 20} more")
    else:
        stats = result.get("stats", {})
        typer.echo(f"Red team evaluation complete: {stats.get('totalTests', 0)} test(s) run")
        typer.echo(f"Vulnerabilities detected: {stats.get('totalFailed', 0)}")


# ===================================================================
#  plugins commands
# ===================================================================


@plugins_app.command("list")
def plugins_list(
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag"),
) -> None:
    """List available red-team plugins."""

    async def _list() -> list:
        plugins = await discover_plugins()
        if category:
            plugins = [p for p in plugins if p.get("category") == category]
        if tag:
            plugins = [p for p in plugins if tag in p.get("tags", [])]
        return sorted(plugins, key=lambda p: p.get("id", ""))

    plugins = asyncio.run(_list())

    table = Table(title="Available Plugins")
    table.add_column("ID", style="cyan")
    table.add_column("Severity", style="magenta")
    table.add_column("Label", style="green")
    table.add_column("Category")
    table.add_column("Tags")

    for p in plugins:
        p_id = p.get("id", "")
        severity = p.get("severity", "")
        label = p.get("label", "")
        cat = p.get("category", "")
        tags = ", ".join(p.get("tags", []))
        table.add_row(p_id, severity, label, cat, tags)

    Console().print(table)
    typer.echo(f"\nTotal plugins: {len(plugins)}")


@plugins_app.command("show")
def plugins_show(
    plugin_id: str = typer.Argument(..., help="Plugin identifier (e.g. hateful, jailbreaking)"),
) -> None:
    """Show detailed information about a specific plugin."""

    async def _show() -> dict:
        manifest = await get_plugin_manifest(plugin_id)
        if not manifest:
            typer.echo(f"Error: Plugin '{plugin_id}' not found.", err=True)
            raise typer.Exit(code=1)
        return manifest

    manifest = asyncio.run(_show())

    typer.echo(f"Plugin: {manifest.get('id', plugin_id)}")
    typer.echo(f"  Label:       {manifest.get('label', 'N/A')}")
    typer.echo(f"  Category:    {manifest.get('category', 'N/A')}")
    typer.echo(f"  Severity:    {manifest.get('severity', 'N/A')}")
    typer.echo(f"  Tags:        {', '.join(manifest.get('tags', []))}")
    typer.echo(f"  Templates:   {manifest.get('template_count', 0)}")
    typer.echo(f"  Description: {manifest.get('description', 'No description available')}")


# ===================================================================
#  providers commands
# ===================================================================


@providers_app.command("test")
def providers_test(
    provider_id: str = typer.Argument(..., help="Provider identifier (e.g. openai:chat:gpt-4.1)"),
    measure_latency: bool = typer.Option(
        False, "--measure-latency", help="Report response latency"
    ),
) -> None:
    """Test a provider connection with a simple probe."""

    async def _test() -> None:
        registry = Registry()
        try:
            provider = registry.get(provider_id)
        except KeyError:
            typer.echo(f"Error: Provider '{provider_id}' not found in registry.", err=True)
            raise typer.Exit(code=1)  # noqa: B904

        typer.echo(f"Testing provider: {provider_id}")

        start = time.monotonic()
        try:
            response = await provider.call_api("Respond with 'OK' only.")
            elapsed = time.monotonic() - start
            is_error = response.get("error") is not None

            typer.echo(f"Status:  {'error' if is_error else 'ok'}")
            output = response.get("output") or response.get("content") or ""
            if output:
                preview = str(output)[:200]
                typer.echo(f"Output:  {preview}")
            if is_error:
                typer.echo(f"Error:   {response.get('error')}")
            if measure_latency:
                typer.echo(f"Latency: {elapsed * 1000:.1f} ms")
        except Exception as exc:
            elapsed = time.monotonic() - start
            typer.echo("Status: error")
            typer.echo(f"Error:  {exc}", err=True)
            if measure_latency:
                typer.echo(f"Latency: {elapsed * 1000:.1f} ms")

    asyncio.run(_test())


@providers_app.command("list")
def providers_list() -> None:
    """List all registered providers."""

    async def _list() -> list:
        registry = Registry()
        return registry.list_registered()

    providers = asyncio.run(_list())

    table = Table(title="Registered Providers")
    table.add_column("Provider ID", style="cyan")
    for pid in sorted(providers):
        table.add_row(pid)

    Console().print(table)
    typer.echo(f"\nTotal providers: {len(providers)}")


# ===================================================================
#  server command (root)
# ===================================================================


@app.command("server")
def server_start(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind address"),
    port: int = typer.Option(15500, "--port", "-p", help="Listen port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload on code changes"),
) -> None:
    """Start the Kitty REST API server."""
    import uvicorn

    typer.echo(f"Starting Kitty server on {host}:{port}")
    uvicorn.run(
        "kitty.server.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


# ===================================================================
#  cache command (root)
# ===================================================================


@app.command("cache")
def cache_command(
    command: str = typer.Argument(..., help="stats | clear"),
    provider: str | None = typer.Option(None, "--provider", help="Filter by provider"),
) -> None:
    """Manage the evaluation response cache."""

    async def _manage() -> None:
        manager = CacheManager()
        if command == "stats":
            stats = await manager.stats()
            typer.echo(json.dumps(stats, indent=2, default=str))
        elif command == "clear":
            await manager.clear(provider=provider)
            msg = "Cache cleared."
            if provider:
                msg += f" (provider: {provider})"
            typer.echo(msg)
        else:
            typer.echo(f"Unknown command: '{command}'. Use 'stats' or 'clear'.", err=True)
            raise typer.Exit(code=1)

    asyncio.run(_manage())


# ===================================================================
#  db command (root)
# ===================================================================


@app.command("db")
def db_command(
    command: str = typer.Argument(..., help="migrate | current | rollback"),
) -> None:
    """Manage the database schema via Alembic."""
    try:
        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig
    except ImportError:
        typer.echo("Error: alembic is not installed. Install with: pip install alembic", err=True)
        raise typer.Exit(code=1)  # noqa: B904

    alembic_cfg = AlembicConfig("alembic.ini")

    if command == "migrate":
        alembic_command.upgrade(alembic_cfg, "head")
        typer.echo("Database migrated to latest version.")
    elif command == "current":
        alembic_command.current(alembic_cfg)
    elif command == "rollback":
        alembic_command.downgrade(alembic_cfg, "-1")
        typer.echo("Rolled back one migration step.")
    else:
        typer.echo(
            f"Unknown command: '{command}'. Use 'migrate', 'current', or 'rollback'.", err=True
        )
        raise typer.Exit(code=1)


# ===================================================================
#  init command (root)
# ===================================================================


@app.command("init")
def init_command(
    example: bool = typer.Option(False, "--example", help="Create a sample configuration file"),
) -> None:
    """Initialize Kitty configuration in the current directory."""
    if example:
        sample = """# Kitty Configuration File
# See https://kitty.dev/docs/config for full documentation

target:
  provider: openai:chat:gpt-4
  prompts:
    - "What is your purpose?"
    - "How can I help you today?"

plugins:
  - id: "hateful"
  - id: "jailbreaking"
  - id: "harmful"

redteam:
  num_tests: 10
  plugin_filter: []

output:
  format: json
"""
        path = os.path.join(os.getcwd(), "kittyconfig.yaml")
        with open(path, "w") as f:
            f.write(sample)
        typer.echo(f"Created sample configuration file: {path}")
    else:
        minimal = """# Kitty Configuration
target:
  provider: openai:chat:gpt-4
  prompts:
    - "Hello, world!"

plugins: []
"""
        path = os.path.join(os.getcwd(), "kittyconfig.yaml")
        with open(path, "w") as f:
            f.write(minimal)
        typer.echo(f"Created configuration file: {path}")
        typer.echo("Run 'kitty init --example' for a more complete example.")


# ===================================================================
#  entry point
# ===================================================================

if __name__ == "__main__":
    app()
