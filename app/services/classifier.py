"""Connects the trained text classifier to the web app.

The model file is loaded once and reloaded only if the file changes. If it is missing or
unreadable, reports are still saved, just without a suggested category.

Privacy: report text is never written to logs, and nothing here returns it.
"""
from pathlib import Path

from flask import current_app

from app.config import BASE_DIR
from app.nlp.classifier import classify, load_artifact

DEFAULT_MODEL_PATH = BASE_DIR / "ml_models" / "incident_classifier.joblib"

_cache = {"key": None, "artifact": None}


def _model_path():
    return Path(current_app.config.get("NLP_MODEL_PATH", DEFAULT_MODEL_PATH))


def load_model():
    """The loaded classifier, or None if there is no usable model file."""
    path = _model_path()
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return None

    if _cache["key"] != key:
        try:
            _cache["artifact"] = load_artifact(path)
        except Exception:
            current_app.logger.warning("Could not load the text classifier at %s", path, exc_info=True)
            _cache["artifact"] = None
        _cache["key"] = key
    return _cache["artifact"]


def classify_description(description):
    """Suggestion for a description, or None if no classifier is available."""
    artifact = load_model()
    if artifact is None:
        return None
    return classify(artifact, description)