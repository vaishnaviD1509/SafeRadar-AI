import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def app(tmp_path):
    """A fresh app with an empty in-memory database for every test.

    The model paths point at files that do not exist, so tests never depend on whether
    you have trained the risk model or the text classifier on your own machine.
    """
    app = create_app("testing")
    app.config["RISK_MODEL_PATH"] = str(tmp_path / "no_model_here.joblib")
    app.config["NLP_MODEL_PATH"] = str(tmp_path / "no_classifier_here.joblib")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()