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

    # Routing service. The public OSRM demo server is for light use only.
    OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org")

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


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True  # cookies only over HTTPS


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}