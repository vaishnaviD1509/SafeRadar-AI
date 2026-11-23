"""Application configuration.

Secrets and environment-specific values come from environment variables
(loaded from the .env file), never hard-coded in the source.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Settings shared by all environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'instance' / 'saferadar.db').as_posix()}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session cookie security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # CSRF protection (Flask-WTF)
    WTF_CSRF_ENABLED = True

    # Map defaults (centred on Kalaburagi, Karnataka)
    DEFAULT_MAP_CENTER = (17.3297, 76.8343)
    DEFAULT_MAP_ZOOM = 13

    # Maximum trusted emergency contacts per user
    MAX_TRUSTED_CONTACTS = 5

    # Incident reporting limits (Phase 4)
    MAX_REPORTS_PER_DAY = 5          # stops spam from one account
    REPORT_MAX_AGE_DAYS = 365        # older incidents cannot be reported

    # Times are stored in UTC. Users type local time, which is converted using
    # this fixed offset. 330 minutes = India Standard Time (UTC+05:30, no daylight saving).
    LOCAL_UTC_OFFSET_MINUTES = 330

    # Routing service (Phase 9). The public OSRM demo server is for light use only and it
    # offers CAR routes only, so times are driving times. For walking routes, use a server
    # that has a foot profile and set both values in your .env file, for example:
    #   OSRM_BASE_URL=https://routing.openstreetmap.de/routed-foot
    #   OSRM_PROFILE=foot
    # (That server is run by someone else: test it before you rely on it.)
    OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org")
    OSRM_PROFILE = os.environ.get("OSRM_PROFILE", "driving")
    OSRM_TIMEOUT_SECONDS = 8

    # Emergency SOS (Phase 10)
    SOS_DURATION_MINUTES = 240       # a share link stops showing a location after this long
    SOS_MAX_PER_HOUR = 5             # stops accidental or abusive repeated alerts
    # The address people outside your network can open, for example your deployed site or a
    # tunnel address. Leave empty while the app only runs on your own computer.
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = True
    # Fallback key so a fresh setup still runs. Never used in production.
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-insecure-key"


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "testing-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    PUBLIC_BASE_URL = ""             # tests never depend on your own .env file


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True  # cookies only over HTTPS


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}