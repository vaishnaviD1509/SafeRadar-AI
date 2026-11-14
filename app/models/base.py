"""Shared model helpers."""
from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    """Current UTC time as a naive datetime (SQLite does not store time zones).
    Every timestamp in this project is UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    """Adds created_at and updated_at columns to any model that uses it."""

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)