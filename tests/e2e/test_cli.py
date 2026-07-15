"""End-to-end smoke tests for the Kitty CLI."""

from __future__ import annotations

import pytest

try:
    from typer.testing import CliRunner
except ImportError:
    CliRunner = None  # type: ignore

pytestmark = pytest.mark.skipif(CliRunner is None, reason="requires typer.testing.CliRunner")


@pytest.fixture(scope="module")
def cli_runner() -> CliRunner:
    """Return a Typer CliRunner for invoking the CLI."""
    return CliRunner()


@pytest.fixture(scope="module")
def kitty_cli() -> object:
    """Import and return the Kitty CLI app."""
    from kitty.cli import app

    return app


class TestCli:
    """End-to-end smoke tests for the Kitty CLI."""

    def test_cli_help_succeeds(self, cli_runner: CliRunner, kitty_cli: object) -> None:
        """Invoking --help should exit with code 0 and show usage."""
        result = cli_runner.invoke(kitty_cli, ["--help"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout or "kitty" in result.stdout.lower()

    def test_cli_plugins_list(self, cli_runner: CliRunner, kitty_cli: object) -> None:
        """Invoking plugins list should show available plugins."""
        result = cli_runner.invoke(kitty_cli, ["plugins", "list"])
        assert result.exit_code == 0
        assert "Total plugins" in result.stdout

    def test_cli_eval_invalid_config(self, cli_runner: CliRunner, kitty_cli: object) -> None:
        """Evaluating with a non-existent config path should produce an error."""
        result = cli_runner.invoke(
            kitty_cli,
            ["eval", "run", "--config", "/tmp/non_existent_config_file.yaml"],
        )
        assert result.exit_code != 0

    def test_cli_version_succeeds(self, cli_runner: CliRunner, kitty_cli: object) -> None:
        """Invoking --version should exit 0 and display a version string."""
        result = cli_runner.invoke(kitty_cli, ["--version"])
        assert result.exit_code == 0
        assert result.stdout.strip()

    def test_cli_server_help(self, cli_runner: CliRunner, kitty_cli: object) -> None:
        """Invoking server --help should show server-specific options."""
        result = cli_runner.invoke(kitty_cli, ["server", "--help"])
        assert result.exit_code == 0
        assert "host" in result.stdout or "port" in result.stdout

    def test_cli_eval_help(self, cli_runner: CliRunner, kitty_cli: object) -> None:
        """Invoking eval --help should show eval-specific options."""
        result = cli_runner.invoke(kitty_cli, ["eval", "--help"])
        assert result.exit_code == 0
        assert "config" in result.stdout

    def test_cli_redteam_help(self, cli_runner: CliRunner, kitty_cli: object) -> None:
        """Invoking redteam --help should show redteam-specific options."""
        result = cli_runner.invoke(kitty_cli, ["redteam", "--help"])
        assert result.exit_code == 0
