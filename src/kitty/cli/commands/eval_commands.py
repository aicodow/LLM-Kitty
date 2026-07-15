"""CLI command implementations — eval, plugins, providers."""
from __future__ import annotations

import asyncio
from typing import Optional

import typer

# ── Eval Commands ─────────────────────────────────────────────────


def run(
    config: str = typer.Option("kittyconfig.yaml", "--config", "-c"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
    no_cache: bool = typer.Option(False, "--no-cache"),
    max_concurrency: Optional[int] = typer.Option(None, "--max-concurrency"),
    resume: bool = typer.Option(False, "--resume"),
    retry_errors: bool = typer.Option(False, "--retry-errors"),
) -> None:
    async def _run() -> None:
        from kitty.pipeline.evaluator import evaluate
        from kitty.config.loader import load_kitty_config
        config_obj = load_kitty_config(config)
        if max_concurrency is not None:
            config_obj.evaluate_options.max_concurrency = max_concurrency
        if no_cache:
            import os
            os.environ["KITTY_DISABLE_CACHE"] = "1"
        typer.echo(f"Starting evaluation: {config_obj.description or config}")
        result = await evaluate(config_obj)
        typer.echo(f"\nResults: {result.stats.totalPassed}/{result.stats.totalTests} passed ({result.stats.passRate:.1%})")
        if result.stats.totalErrors:
            typer.echo(f"Errors: {result.stats.totalErrors}")
        if output:
            from pathlib import Path
            Path(output).write_text(result.model_dump_json(indent=2), encoding="utf-8")
            typer.echo(f"Results exported to: {output}")
    asyncio.run(_run())


def list_evals(
    limit: int = typer.Option(20, "--limit", "-l"),
) -> None:
    async def _list() -> None:
        from kitty.database import get_session, init_db
        from sqlalchemy import select
        from kitty.database.models import Evaluation
        await init_db()
        async for session in get_session():
            result = await session.execute(select(Evaluation).order_by(Evaluation.created_at.desc()).limit(limit))
            for e in result.scalars().all():
                typer.echo(f"{e.id[:8]}  {e.created_at.isoformat()[:19]}  {e.status:12s}  {e.pass_rate:.0%}")
    asyncio.run(_list())


def redteam_run(
    config: str = typer.Option("kittyconfig.yaml", "--config", "-c"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    typer.echo(f"Red-team scan from: {config}")


# ── Plugins Commands ─────────────────────────────────────────────


def list_plugins(
    category: Optional[str] = typer.Option(None, "--category", "-c"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t"),
) -> None:
    async def _list() -> None:
        from kitty.redteam.plugins import PluginRegistry
        registry = PluginRegistry()
        await registry.discover_all()
        plugins = registry.list_all()
        if category:
            plugins = registry.list_by_category(category)
        if tag:
            plugins = registry.list_by_tag(tag)
        for p in plugins:
            typer.echo(f"  {p.id:<40} [{p.severity.value:<8}] {p.label}")
    asyncio.run(_list())


def show_plugin(plugin_id: str = typer.Argument(..., help="Plugin ID")) -> None:
    async def _show() -> None:
        from kitty.redteam.plugins import PluginRegistry
        registry = PluginRegistry()
        await registry.discover_all()
        m = registry.get_manifest(plugin_id)
        if m is None:
            typer.echo(f"Plugin not found: {plugin_id}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"ID:          {m.id}")
        typer.echo(f"Label:       {m.label}")
        typer.echo(f"Category:    {m.category}")
        typer.echo(f"Severity:    {m.severity.value}")
        typer.echo(f"Tags:        {', '.join(m.tags)}")
        typer.echo(f"Templates:   {len(m.templates)}")
        typer.echo(f"Assertions:  {len(m.assertions)}")
    asyncio.run(_show())


# ── Providers Commands ───────────────────────────────────────────


def test_provider(
    provider_id: str = typer.Argument(..., help="Provider ID to test"),
    measure_latency: bool = typer.Option(False, "--measure-latency"),
) -> None:
    async def _test() -> None:
        import time
        from kitty.providers import ProviderRegistry
        registry = ProviderRegistry()
        typer.echo(f"Testing provider: {provider_id} ...")
        start = time.monotonic()
        try:
            provider = await registry.create(provider_id)
            response = await provider.call_api("Respond with 'OK' only.")
            elapsed = time.monotonic() - start
            typer.echo(f"  Status:    OK")
            typer.echo(f"  Output:    {response.output[:100]}")
            typer.echo(f"  Latency:   {elapsed:.2f}s")
        except Exception as exc:
            typer.echo(f"  Status:    ERROR — {exc}", err=True)
            raise typer.Exit(code=1)
    asyncio.run(_test())


def list_providers() -> None:
    async def _list() -> None:
        from kitty.providers import ProviderRegistry
        registry = ProviderRegistry()
        await registry.discover_builtins()
        for pid in registry.list_registered():
            typer.echo(f"  {pid}")
    asyncio.run(_list())
