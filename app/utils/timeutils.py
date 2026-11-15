"""Conversion between local time (what users see and type) and UTC (what is stored).

The database always holds UTC. Users in India type and read India Standard Time.
The offset comes from LOCAL_UTC_OFFSET_MINUTES in config.py.
"""
from datetime import timedelta

from flask import current_app

from app.models.base import utcnow


def _offset():
    return timedelta(minutes=current_app.config["LOCAL_UTC_OFFSET_MINUTES"])


def to_utc(local_time):
    """Local time typed by a user -> UTC for storage."""
    return local_time - _offset()


def to_local(utc_time):
    """UTC from the database -> local time for display."""
    return utc_time + _offset()


def local_now():
    """The current local time, without seconds precision concerns."""
    return utcnow() + _offset()