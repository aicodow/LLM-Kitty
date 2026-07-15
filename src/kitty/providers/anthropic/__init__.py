"""Anthropic Messages provider with Extended Thinking and Tool Use support.

Provider ID format: ``anthropic:messages:<model>``
(e.g. ``anthropic:messages:claude-sonnet-4-20250514``).
"""

from kitty.providers.anthropic.messages import AnthropicMessagesProvider

__all__ = ["AnthropicMessagesProvider"]
