"""Pydantic models for Kitty configuration objects.

Defines the configuration schema used to declare evaluation targets,
red-team strategies, output formats, tracing, and top-level run parameters.
Configuration can be loaded from YAML files or constructed programmatically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel as _PydanticBaseModel
from pydantic import ConfigDict, Field, field_validator, model_validator

from kitty.types.eval import Severity, TargetType


class BaseModel(_PydanticBaseModel):
    """Base model for all Kitty types with camelCase/JSON compatibility."""

    model_config = ConfigDict(populate_by_name=True)


# ── Target Configuration ─────────────────────────────────────────────────


class TargetConfig(BaseModel):
    """Configuration for a single evaluation target.

    Attributes:
        id: Unique identifier for this target.
        provider: Provider identifier string or inline ProviderConfig.
        config: Provider-specific configuration dictionary.
        label: Optional human-readable label for this target.
    """

    id: str = Field(min_length=1)
    provider: str | ProviderConfig
    config: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None


# ── Evaluation Options ───────────────────────────────────────────────────


class EvaluateOptions(BaseModel):
    """Runtime options controlling evaluation execution behaviour.

    Attributes:
        max_concurrency: Maximum number of concurrent evaluation workers.
        timeout_ms: Per-request timeout in milliseconds.
        max_eval_time_ms: Maximum total evaluation wall-clock time.
        cache: Whether to cache provider responses.
        delay: Artificial delay (seconds) between requests to avoid rate limits.
        show_progress_bar: Whether to display a progress bar during evaluation.
        filter_first_n: Only evaluate the first N test cases.
        filter_sample: Randomly sample N test cases for evaluation.
        filter_sample_seed: Seed for reproducible random sampling.
    """

    max_concurrency: int = Field(default=4, ge=1, le=20, alias="maxConcurrency")
    timeout_ms: int = Field(default=30000, alias="timeoutMs")
    max_eval_time_ms: int = Field(default=300000, alias="maxEvalTimeMs")
    cache: bool = True
    delay: int = 0
    show_progress_bar: bool = Field(default=True, alias="showProgressBar")
    filter_first_n: int | None = Field(default=None, alias="filterFirstN")
    filter_sample: int | None = Field(default=None, alias="filterSample")
    filter_sample_seed: int | None = Field(default=None, alias="filterSampleSeed")


# ── Red Team Configuration ───────────────────────────────────────────────


class RedteamPluginRef(BaseModel):
    """Reference to a red-team plugin with optional overrides.

    Attributes:
        id: Plugin identifier (e.g. \"harmful:disallowed\").
        num_tests: Number of tests to generate for this plugin.
        config: Plugin-specific configuration overrides.
    """

    id: str
    num_tests: int | None = Field(default=None, alias="numTests")
    config: dict[str, Any] = Field(default_factory=dict)


class RedteamConfig(BaseModel):
    """Configuration for automated red-team test generation.

    Attributes:
        purpose: Description of the target system's purpose (guides generation).
        plugins: List of plugin identifiers or plugin reference objects.
        strategies: List of strategy identifiers or inline strategy config dicts.
        num_tests: Default number of tests to generate per plugin.
        language: Language for generated tests (ISO code, default \"en\").
        target_type: Optional category of the target system.
        severity: Optional severity threshold for findings.
    """

    purpose: str | None = None
    plugins: list[str | RedteamPluginRef] = Field(default_factory=list)
    strategies: list[str | dict[str, Any]] = Field(default_factory=list)
    num_tests: int = Field(default=5, alias="numTests")
    language: str = "en"
    target_type: TargetType | None = Field(default=None, alias="targetType")
    severity: Severity | None = None


# ── Tracing Configuration ────────────────────────────────────────────────


class TracingConfig(BaseModel):
    """Configuration for observability / tracing of evaluation runs.

    Attributes:
        enabled: Whether tracing is active.
        exporter: Tracing exporter type.
        endpoint: Optional endpoint URL for the tracing backend.
    """

    enabled: bool = False
    exporter: Literal["otlp", "console", "none"] = "none"
    endpoint: str | None = None


# ── Output Configuration ─────────────────────────────────────────────────


class OutputConfig(BaseModel):
    """Configuration for a single output destination.

    Attributes:
        format: Output format for results.
        path: Optional filesystem path for the output file.
    """

    format: Literal["json", "csv", "html", "sarif"] = "json"
    path: Path | None = None


# ── Top-Level Configuration ──────────────────────────────────────────────


class KittyConfig(BaseModel):
    """Top-level configuration for a Kitty evaluation run.

    Attributes:
        description: Free-text description of this evaluation.
        targets: One or more targets to evaluate.
        prompts: List of prompt strings or prompt dicts.
        tests: List of test case dicts or inline test identifiers.
        redteam: Optional red-team configuration for automated test generation.
        tracing: Tracing / observability configuration.
        evaluate_options: Runtime evaluation options.
        output: List of output destination configurations.
        env: Environment variables to set during the run.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    description: str = ""
    targets: list[TargetConfig] = Field(min_length=1)
    prompts: list[str | dict[str, Any]] = Field(default_factory=list)
    tests: list[str | dict[str, Any]] = Field(default_factory=list)
    redteam: RedteamConfig | None = None
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    evaluate_options: EvaluateOptions = Field(
        default_factory=EvaluateOptions, alias="evaluateOptions"
    )
    output: list[OutputConfig] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_prompts_tests_or_redteam(self) -> KittyConfig:
        """Ensure at least one of prompts, tests, or redteam is configured."""
        if not self.prompts and not self.tests and self.redteam is None:
            raise ValueError("At least one of 'prompts', 'tests', or 'redteam' must be provided.")
        return self

    @model_validator(mode="after")
    def _ensure_unique_target_ids(self) -> KittyConfig:
        """Validate that all target IDs are unique."""
        ids = [t.id for t in self.targets]
        if len(ids) != len(set(ids)):
            duplicates = {i for i in ids if ids.count(i) > 1}
            raise ValueError(f"Target IDs must be unique; duplicates found: {duplicates}")
        return self

    @field_validator("targets")
    @classmethod
    def _validate_target_ids_not_empty(cls, v: list[TargetConfig]) -> list[TargetConfig]:
        """Ensure each target has a non-empty id after stripping whitespace."""
        for target in v:
            if not target.id.strip():
                raise ValueError("Each target must have a non-empty 'id' field.")
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> KittyConfig:
        """Load configuration from a YAML file.

        Args:
            path: Filesystem path to the YAML configuration file.

        Returns:
            A fully validated KittyConfig instance.

        Raises:
            ConfigNotFoundError: If the file does not exist.
            ConfigValidationError: If the YAML content fails validation.
        """
        from kitty.exceptions import ConfigNotFoundError, ConfigValidationError

        resolved = Path(path)
        if not resolved.exists():
            raise ConfigNotFoundError(f"Configuration file not found: {resolved}")

        # Lazy import so PyYAML is an optional dependency.
        try:
            import yaml
        except ImportError as err:
            raise ImportError(
                "PyYAML is required to load configuration from YAML. "
                "Install it with: pip install pyyaml"
            ) from err

        with resolved.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict):
            raise ConfigValidationError(
                f"YAML file must contain a top-level mapping, got {type(data).__name__}"
            )

        return cls(**data)


# Forward reference needed for TargetConfig.provider union.
# Import here (rather than at top) to avoid circular import at module level.
from kitty.types.eval import ProviderConfig  # noqa: E402

TargetConfig.model_rebuild()


__all__ = [
    "EvaluateOptions",
    "KittyConfig",
    "OutputConfig",
    "RedteamConfig",
    "RedteamPluginRef",
    "TargetConfig",
    "TracingConfig",
]
