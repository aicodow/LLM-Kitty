"""Database layer for the Kitty red teaming framework.

Provides SQLAlchemy async models and session management for storing
evaluation results, caching LLM responses, and auditing.
"""

from __future__ import annotations

from kitty.database.models import AuditLog, Base, CacheEntry, EvalResult, Evaluation, Team
from kitty.database.session import close_db, get_session, init_db

__all__ = [
    "AuditLog",
    "Base",
    "CacheEntry",
    "EvalResult",
    "Evaluation",
    "Team",
    "close_db",
    "get_session",
    "init_db",
]
