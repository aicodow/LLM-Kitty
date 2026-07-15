"""Plugin manifest definition for the Kitty red teaming framework.

PluginManifest describes the metadata, templates, assertions, and
variable schemas for a single red team test plugin.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, enum.Enum):
    """Severity levels for red team test findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PluginManifest(BaseModel):
    """Metadata and configuration for a red team test plugin.

    A PluginManifest describes everything needed to generate test cases:
    template strings, assertion rules, variable values, and metadata
    for categorization and filtering.

    Attributes:
        id: Unique plugin identifier (e.g. ``"foundation:pii"``).
        label: Human-readable display name.
        description: Detailed explanation of what the plugin tests.
        category: Plugin category namespace (default ``"custom"``).
        severity: Default severity for findings from this plugin.
        tags: Arbitrary classification tags.
        templates: Jinja2 template strings for generating prompts.
        assertions: Assertion dictionaries passed to each test case.
        vars: Dictionary mapping variable names to lists of values.
        num_tests: Default number of tests to generate (default 5, min 1).
        requires_purpose: Whether a target purpose string is required.
        requires_entities: Whether entity lists are required.
        supported_providers: Restrict to these provider IDs (empty = all).
        plugin_class: Fully-qualified class reference (``"module:ClassName"``).
    """

    id: str = Field(description="Unique plugin identifier (e.g. 'foundation:pii')")
    label: str = Field(description="Human-readable display name")
    description: str = Field(default="", description="Detailed explanation of the plugin")
    category: str = Field(default="custom", description="Plugin category namespace")
    severity: Severity = Field(default=Severity.MEDIUM, description="Default finding severity")
    tags: list[str] = Field(default_factory=list, description="Classification tags")
    templates: list[str] = Field(default_factory=list, description="Jinja2 prompt templates")
    assertions: list[dict[str, Any]] = Field(
        default_factory=list, description="Assertion rule dictionaries"
    )
    vars: dict[str, list[str]] = Field(
        default_factory=dict, description="Template variable name to value-list mappings"
    )
    num_tests: int = Field(default=5, ge=1, description="Default number of tests to generate")
    requires_purpose: bool = Field(
        default=True, description="Whether a target purpose string is required"
    )
    requires_entities: bool = Field(
        default=False, description="Whether entity lists are required"
    )
    supported_providers: list[str] = Field(
        default_factory=list,
        description="Provider IDs this plugin supports (empty = all)",
    )
    plugin_class: str | None = Field(
        default=None,
        description="Fully-qualified class reference, e.g. 'my_module:MyPlugin'",
    )

    def __str__(self) -> str:
        """Return a short human-readable representation."""
        return f"{self.id} ({self.label})"

    def __repr__(self) -> str:
        """Return an unambiguous representation."""
        return (
            f"PluginManifest(id={self.id!r}, label={self.label!r}, "
            f"category={self.category!r}, severity={self.severity.value!r})"
        )
