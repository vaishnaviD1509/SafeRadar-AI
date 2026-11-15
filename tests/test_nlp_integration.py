import logging
from datetime import datetime

import pytest

from app.extensions import db
from app.models import IncidentReport
from app.nlp.classifier import save_artifact
from app.services import reports as report_service
from app.services.reports import create_report
from tests.helpers import login, make_user
from tests.nlp_helpers import trained_nlp

STALKING = "A man followed me for several minutes from the bus stand at night and I felt scared."
GIBBERISH = "xyzzy qwerty zzzz plugh wibble wobble foo bar"
WHEN = datetime(2026, 5, 1, 20, 0)


@pytest.fixture
def with_classifier(app, tmp_path):
    path = tmp_path / "incident_classifier.joblib"
    save_artifact(trained_nlp()["artifact"], path)
    app.config["NLP_MODEL_PATH"] = str(path)
    return path


def new_report(user, description):
    return create_report(user, description=description, severity=3, local_time=WHEN,
                         latitude=17.33, longitude=76.83)


# ---------- saving a report ----------

def test_confident_text_gets_a_suggested_category(app, with_classifier):
    report = new_report(make_user(), STALKING)
    assert report.category == "Stalking"
    assert 0.5 <= report.category_confidence <= 1
    assert report.status == "pending"                 # still needs an administrator
    assert report.is_synthetic is False


def test_unsure_text_stays_uncategorised(app, with_classifier):
    report = new_report(make_user(), GIBBERISH)
    assert report.category is None
    assert report.category_confidence is None
    assert report.status == "pending"


def test_without_a_classifier_the_report_is_still_saved(app):
    report = new_report(make_user(), STALKING)
    assert report.id is not None
    assert report.category is None


def test_a_failing_classifier_never_loses_the_report(app, monkeypatch):
    def broken(_text):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(report_service, "classify_description", broken)
    report = new_report(make_user(), STALKING)
    assert report.id is not None
    assert report.category is None


def test_a_damaged_model_file_is_handled_without_logging_text(app, tmp_path, caplog):
    broken = tmp_path / "broken.joblib"
    broken.write_bytes(b"not a model")
    app.config["NLP_MODEL_PATH"] = str(broken)
    with caplog.at_level(logging.DEBUG):
        report = new_report(make_user(), STALKING)
    assert report.id is not None and report.category is None
    assert STALKING not in caplog.text                 # report text never reaches the logs


def test_submitting_the_form_classifies_the_report(client, app, with_classifier):
    user = make_user()
    login(client, email=user.email)
    response = client.post("/report", data={
        "description": STALKING, "severity": "3", "incident_time": "2026-05-01T20:00",
        "latitude": "17.33", "longitude": "76.83", "confirm": "y",
    })
    assert response.status_code == 302
    assert IncidentReport.query.one().category == "Stalking"


# ---------- what the user sees ----------

def test_my_reports_labels_the_category_as_a_suggestion(client, app, with_classifier):
    user = make_user()
    new_report(user, STALKING)
    login(client, email=user.email)
    page = client.get("/my-reports").data
    assert b"Stalking" in page
    assert b"Suggested" in page
    assert b"% sure" in page


def test_my_reports_says_awaiting_when_there_is_no_category(client, app):
    user = make_user()
    new_report(user, STALKING)
    login(client, email=user.email)
    page = client.get("/my-reports").data
    assert b"Awaiting classification" in page
    assert b"Suggested" not in page


def test_pending_suggestions_stay_hidden_from_others(client, app, with_classifier):
    new_report(make_user("author@example.com"), STALKING)
    other = make_user("other@example.com")
    login(client, email=other.email)
    page = client.get("/dashboard").data
    assert b"Stalking" in page                          # the category list always names every type
    assert STALKING.encode() not in page
    assert b"No approved incidents to show yet" in page


# ---------- command line ----------

def test_classify_reports_fills_in_missing_categories(app, with_classifier):
    user = make_user()
    sure = IncidentReport(user_id=user.id, latitude=17.33, longitude=76.83, description=STALKING,
                          severity=3, incident_time=WHEN)
    unsure = IncidentReport(user_id=user.id, latitude=17.33, longitude=76.83, description=GIBBERISH,
                            severity=3, incident_time=WHEN)
    db.session.add_all([sure, unsure])
    db.session.commit()

    result = app.test_cli_runner().invoke(args=["classify-reports"])
    assert result.exit_code == 0, result.output
    assert "Checked 2 reports" in result.output
    assert "1 got a suggestion, 1 left for an administrator" in result.output
    assert STALKING not in result.output                # report text is never printed
    db.session.refresh(sure)
    db.session.refresh(unsure)
    assert sure.category == "Stalking"
    assert unsure.category is None


def test_classify_reports_leaves_existing_categories_alone(app, with_classifier):
    user = make_user()
    done = IncidentReport(user_id=user.id, latitude=17.33, longitude=76.83, description=STALKING,
                          severity=3, incident_time=WHEN, category="Threats")
    db.session.add(done)
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["classify-reports"])
    assert "Checked 0 reports" in result.output
    db.session.refresh(done)
    assert done.category == "Threats"


def test_classify_reports_needs_a_trained_model(app):
    result = app.test_cli_runner().invoke(args=["classify-reports"])
    assert result.exit_code != 0
    assert "train_classifier" in result.output