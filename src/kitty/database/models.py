"""SQLAlchemy 2.0 async ORM models for the Kitty red teaming framework.

Defines the database schema for evaluations, results, caching,
teams, and audit logging.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Declarative base for all Kitty ORM models."""

    type_annotation_map = {
        dict[str, Any]: JSON,
        dict[str, str]: JSON,
    }


def _uuid_str() -> str:
    """Generate a UUID4 hex string (without dashes)."""
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Evaluation
# ------------------------------------------------------------------


class Evaluation(Base):
    """A single red team evaluation run.

    Stores the overall configuration, status, and aggregate metrics
    for a set of adversarial tests executed against one or more
    providers.
    """

    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    config_blob: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        nullable=False,
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)

    total_tests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    results: Mapped[list["EvalResult"]] = relationship(
        "EvalResult",
        back_populates="evaluation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        """Return a short representation of the evaluation."""
        return f"Evaluation(id={self.id!r}, status={self.status!r}, pass_rate={self.pass_rate:.2f})"


# ------------------------------------------------------------------
# EvalResult
# ------------------------------------------------------------------


class EvalResult(Base):
    """A single test result within an evaluation.

    Captures the prompt sent, the response received, pass/fail status,
    score, and metadata for auditing.
    """

    __tablename__ = "eval_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    evaluation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(256), nullable=False)
    prompt_raw: Mapped[str] = mapped_column(Text, nullable=False)
    response_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_token_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    plugin_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, index=True)
    strategy_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    metadata_blob: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    # Relationships
    evaluation: Mapped["Evaluation"] = relationship("Evaluation", back_populates="results")

    def __repr__(self) -> str:
        """Return a short representation of the eval result."""
        return f"EvalResult(id={self.id!r}, passed={self.passed}, plugin_id={self.plugin_id!r})"


# ------------------------------------------------------------------
# CacheEntry
# ------------------------------------------------------------------


class CacheEntry(Base):
    """Cache of LLM responses to avoid redundant API calls.

    Uniquely identified by ``(cache_key, provider_id)``.
    """

    __tablename__ = "cache_entries"
    __table_args__ = (UniqueConstraint("cache_key", "provider_id", name="uq_cache_key_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_blob: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=86400, nullable=False)

    def __repr__(self) -> str:
        """Return a short representation of the cache entry."""
        return (
            f"CacheEntry(id={self.id}, cache_key={self.cache_key!r}, "
            f"provider_id={self.provider_id!r})"
        )


# ------------------------------------------------------------------
# Team
# ------------------------------------------------------------------


class Team(Base):
    """A team or organization within Kitty.

    Used for multi-tenant deployments and team-scoped evaluations.
    """

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        """Return a short representation of the team."""
        return f"Team(id={self.id!r}, name={self.name!r})"


# ------------------------------------------------------------------
# AuditLog
# ------------------------------------------------------------------


class AuditLog(Base):
    """Audit trail for sensitive operations.

    Captures who did what, when, and from where for security auditing.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(256), nullable=False)
    resource: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    metadata_blob: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, nullable=False, index=True
    )

    def __repr__(self) -> str:
        """Return a short representation of the audit log entry."""
        return f"AuditLog(id={self.id}, user_id={self.user_id!r}, action={self.action!r})"
