"""Exception hierarchy for the Kitty LLM red-teaming framework.

All custom exceptions derive from KittyError, providing a consistent base
for error handling throughout the framework.
"""


class KittyError(Exception):
    """Base exception for all Kitty framework errors."""

    pass


# ── Configuration Errors ─────────────────────────────────────────────────


class ConfigError(KittyError):
    """Raised when there is a general configuration problem."""

    pass


class ConfigValidationError(ConfigError):
    """Raised when configuration fails Pydantic validation."""

    pass


class ConfigNotFoundError(ConfigError):
    """Raised when a configuration file or resource cannot be located."""

    pass


# ── Provider Errors ──────────────────────────────────────────────────────


class ProviderError(KittyError):
    """Raised when an LLM provider encounters a general issue."""

    pass


class ProviderConnectionError(ProviderError):
    """Raised when a connection to the provider cannot be established."""

    pass


class ProviderAuthError(ProviderError):
    """Raised when authentication with the provider fails."""

    pass


class ProviderRateLimitError(ProviderError):
    """Raised when the provider rate-limits the request."""

    pass


# ── Evaluation Errors ────────────────────────────────────────────────────


class EvalError(KittyError):
    """Raised when an evaluation run encounters a general failure."""

    pass


class EvalTimeoutError(EvalError):
    """Raised when an evaluation exceeds the configured time limit."""

    pass


class EvalInterruptedError(EvalError):
    """Raised when an evaluation is interrupted (e.g. by the user)."""

    pass


# ── Cache Errors ─────────────────────────────────────────────────────────


class CacheError(KittyError):
    """Raised when a caching operation fails."""

    pass


# ── Security Errors ──────────────────────────────────────────────────────


class SecurityError(KittyError):
    """Raised when a security violation is detected."""

    pass


class PathTraversalError(SecurityError):
    """Raised when a path traversal attack is detected."""

    pass


class PromptInjectionDetectedError(SecurityError):
    """Raised when prompt injection is detected in user or system input."""

    pass


__all__ = [
    "CacheError",
    "ConfigError",
    "ConfigNotFoundError",
    "ConfigValidationError",
    "EvalError",
    "EvalInterruptedError",
    "EvalTimeoutError",
    "KittyError",
    "PathTraversalError",
    "PromptInjectionDetectedError",
    "ProviderAuthError",
    "ProviderConnectionError",
    "ProviderError",
    "ProviderRateLimitError",
    "SecurityError",
]
