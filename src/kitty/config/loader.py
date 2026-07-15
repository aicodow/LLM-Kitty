"""Safe YAML configuration loader with environment variable resolution."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::-(.*?))?\}")
"""Matches ``${VAR}`` and ``${VAR:-default}`` environment variable references."""

MAX_ALIAS_DEPTH = 10
"""Maximum nesting depth for YAML aliases (Billion Laughs protection)."""


# ---------------------------------------------------------------------------
# Safe YAML loader
# ---------------------------------------------------------------------------


class SafeYamlLoader(yaml.SafeLoader):
    """YAML loader that limits alias depth to prevent Billion Laughs attacks.

    Extends :class:`yaml.SafeLoader` with depth tracking on alias nodes
    and an explicit resolver depth cap.
    """

    def __init__(self, stream) -> None:
        super().__init__(stream)
        self._alias_depth = 0
        # Limit resolver depth to prevent deep recursion during type resolution
        if hasattr(self, "resolver") and hasattr(self.resolver, "max_depth"):
            self.resolver.max_depth = 6

    def construct_object(self, node, deep: bool = False) -> Any:
        """Override to track alias depth and prevent exponential expansion."""
        if isinstance(node, yaml.nodes.AliasNode):
            self._alias_depth += 1
            if self._alias_depth > MAX_ALIAS_DEPTH:
                raise yaml.constructor.ConstructorError(
                    None,
                    None,
                    f"maximum alias depth ({MAX_ALIAS_DEPTH}) exceeded "
                    f"(possible Billion Laughs attack)",
                    node.start_mark,
                )
            try:
                return super().construct_object(node, deep=deep)
            finally:
                self._alias_depth -= 1
        return super().construct_object(node, deep=deep)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def safe_resolve_path(path: str) -> Path:
    """Resolve *path* safely, preventing traversal outside allowed directories.

    Allowed base directories are the current working directory and
    ``~/.kitty/``.

    Args:
        path: File path to resolve.  May include ``~`` for the home
            directory.

    Returns:
        Resolved absolute :class:`~pathlib.Path`.

    Raises:
        ValueError: If the resolved path falls outside any allowed
            base directory.
    """
    resolved = Path(path).expanduser().resolve()
    allowed: List[Path] = [
        Path.cwd().resolve(),
        Path("~/.kitty").expanduser().resolve(),
    ]

    for base in allowed:
        if resolved == base or base in resolved.parents:
            return resolved

    raise ValueError(
        f"path '{path}' resolves to '{resolved}', which is outside "
        f"allowed directories: {[str(d) for d in allowed]}"
    )


# ---------------------------------------------------------------------------
# Environment variable resolution
# ---------------------------------------------------------------------------


def resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ``${VAR}`` and ``${VAR:-default}`` patterns.

    Args:
        value: A string, dict, list, or scalar value that may contain
            environment variable references.

    Returns:
        Value with all environment variable references resolved in-place.
    """
    if isinstance(value, str):

        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            if default is not None:
                return os.environ.get(var_name, default)
            return os.environ.get(var_name, "")

        return ENV_VAR_PATTERN.sub(_replace, value)

    if isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}

    if isinstance(value, list):
        return [resolve_env_vars(item) for item in value]

    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_yaml_config(path: str) -> Dict[str, Any]:
    """Load a YAML configuration file and resolve all environment variables.

    Args:
        path: Path to the YAML file.  Must resolve within an allowed
            directory (see :func:`safe_resolve_path`).

    Returns:
        Dictionary of configuration values with ``${VAR}`` references
        resolved.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the YAML content is invalid or the Billion
            Laughs depth limit is exceeded.
        ValueError: If *path* is outside allowed directories.
    """
    resolved_path = safe_resolve_path(path)
    with open(resolved_path, "r", encoding="utf-8") as f:
        data: Optional[Dict[str, Any]] = yaml.load(f, Loader=SafeYamlLoader)
    return resolve_env_vars(data or {})


# ---------------------------------------------------------------------------
# Pydantic config model
# ---------------------------------------------------------------------------


class KittyConfig(BaseModel):
    """Pydantic model for Kitty framework configuration.

    Attributes:
        providers: Mapping of provider identifiers to their configuration.
        default_provider: Default provider to use when none is specified.
        max_tokens: Maximum tokens for generated responses.
        temperature: Sampling temperature (0.0 – 2.0).
        timeout: Request timeout in seconds.
        log_level: Logging verbosity level.
        plugins: List of plugin module paths to load.
    """

    model_config = {"extra": "forbid"}

    providers: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Provider configurations keyed by provider ID",
    )
    default_provider: str = Field(
        default="openai:chat",
        description="Default provider identifier",
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        description="Maximum tokens in generated responses",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    timeout: int = Field(
        default=60,
        ge=1,
        description="Request timeout in seconds",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    plugins: List[str] = Field(
        default_factory=list,
        description="Plugin module paths to load",
    )


def load_kitty_config(path: str) -> KittyConfig:
    """Load and validate a Kitty configuration file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A validated :class:`KittyConfig` instance.

    Raises:
        pydantic.ValidationError: If the configuration fails validation.
    """
    data = load_yaml_config(path)
    return KittyConfig.model_validate(data)
