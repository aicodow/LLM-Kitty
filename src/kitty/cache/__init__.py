"""Cache package for Kitty framework.

Provides a two-tier caching layer using diskcache as the primary store
and Redis as an optional secondary cache.
"""

from .manager import CacheManager

__all__ = [
    "CacheManager",
]
