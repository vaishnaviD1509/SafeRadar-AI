"""Connects the trained risk model to the web app.

The model file is loaded once and kept in memory. It is loaded again only if the file
changes (for example after you retrain). If the file is missing or unreadable the app
keeps working and simply shows "no estimate": it never invents a risk level.
"""
from pathlib import Path

from flask import current_app

from app.config import BASE_DIR
from app.ml.risk_model import load_artifact, predict_risk
from app.utils.timeutils import local_now

DEFAULT_MODEL_PATH = BASE_DIR / "ml_models" / "risk_model.joblib"

_cache = {"key": None, "artifact": None}


def _model_path():
    return Path(current_app.config.get("RISK_MODEL_PATH", DEFAULT_MODEL_PATH))


def load_model():
    """The loaded model, or None if there is no usable model file."""
    path = _model_path()
    try:
        key = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return None                      # file does not exist

    if _cache["key"] != key:
        try:
            _cache["artifact"] = load_artifact(path)
        except Exception:                # damaged file, wrong version, missing library...
            current_app.logger.warning("Could not load the risk model at %s", path, exc_info=True)
            _cache["artifact"] = None
        _cache["key"] = key
    return _cache["artifact"]


def estimate_risk(lat, lon, when_local=None):
    """Risk estimate for a place and a local time, or None if no model is available."""
    artifact = load_model()
    if artifact is None:
        return None
    return predict_risk(artifact, lat, lon, when_local or local_now())


def get_model_info():
    artifact = load_model()
    return None if artifact is None else artifact["info"]