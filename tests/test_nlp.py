import joblib
import numpy as np
import pytest

from app.ml.synthetic import _TEMPLATES
from app.ml.zones import CATEGORIES
from app.nlp.check_sentences import CHECK_SENTENCES
from app.nlp.classifier import (
    LABELS, classify, coverage_table, grouped_folds, load_artifact, save_artifact, save_charts,
    save_metrics,
)
from app.nlp.groups import template_key
from app.nlp.text import normalize_text
from tests.nlp_helpers import trained_nlp
from tests.risk_helpers import clean_data

STALKING = "A man followed me for several minutes from the bus stand at night and I felt scared."
UNSAFE = "The street lights were not working near the market and the road was completely dark."


# ---------- text cleaning ----------

def test_normalize_lowercases_stems_and_drops_filler_words():
    assert normalize_text("A man was FOLLOWING me!!") == "man follow"
    assert normalize_text("He followed me, she follows me") == "follow follow"


def test_normalize_keeps_negations_and_drops_numbers():
    assert normalize_text("There was NO light at 9pm") == "no light pm"
    assert "not" in normalize_text("lights were not working").split()


def test_normalize_handles_anything_that_is_not_text():
    for value in (None, 123, "", "   ", "12345 !!!", ["a list"]):
        assert normalize_text(value) == ""


# ---------- sentence templates ----------

def test_template_key_ignores_place_time_and_ending():
    a = "A man followed me for several minutes from the bus stand at night and I had to enter a shop to feel safe."
    b = ("A man followed me for several minutes from the railway station in the morning and I had to "
         "enter a shop to feel safe. Please look into this.")
    assert template_key(a) == template_key(b)


def test_template_key_separates_different_templates():
    assert template_key(STALKING) != template_key(UNSAFE)


def test_synthetic_data_has_exactly_one_key_per_template():
    expected = sum(len(items) for items in _TEMPLATES.values())
    assert clean_data()["description"].map(template_key).nunique() == expected


def test_real_text_is_grouped_by_itself():
    assert template_key("  Someone Followed Me Home ") == template_key("someone followed me home")
    assert template_key("one thing") != template_key("another thing")


def test_folds_never_share_a_template_and_cover_everything():
    df = clean_data()
    labels, groups = df["category"].to_numpy(), df["description"].map(template_key).to_numpy()
    seen = []
    for train_idx, test_idx in grouped_folds(labels, groups):
        assert not set(groups[train_idx]) & set(groups[test_idx])
        assert set(labels[train_idx]) == set(CATEGORIES)          # training still sees every category
        seen.extend(test_idx)
    assert sorted(seen) == list(range(len(df)))


# ---------- honest metrics ----------

def test_metrics_are_measured_and_add_up():
    result = trained_nlp()
    rows = result["info"]["rows"]
    cv = result["metrics"]["grouped_cross_validation"]
    assert set(cv) == {"majority_baseline", "naive_bayes", "logistic_regression"}
    for name, m in cv.items():
        matrix = np.array(m["confusion_matrix"])
        assert matrix.sum() == rows, name
        assert m["accuracy"] == pytest.approx(np.trace(matrix) / rows, abs=1e-4)
        assert sum(c["support"] for c in m["per_category"].values()) == rows


def test_new_wording_beats_a_blind_guess_but_random_split_is_inflated():
    metrics = trained_nlp()["metrics"]
    cv = metrics["grouped_cross_validation"]
    assert cv["logistic_regression"]["macro_f1"] > cv["majority_baseline"]["macro_f1"]
    inflated = metrics["random_split_inflated"]["logistic_regression"]["accuracy"]
    assert inflated > cv["logistic_regression"]["accuracy"]


def test_hand_written_check_uses_unseen_sentences():
    texts = {t for t, _ in CHECK_SENTENCES}
    assert len(CHECK_SENTENCES) == 32
    assert {label for _, label in CHECK_SENTENCES} == set(CATEGORIES)
    assert not texts & set(clean_data()["description"])          # never in the training data
    check = trained_nlp()["metrics"]["hand_written_check"]
    assert check["sentences"] == 32
    assert 0 <= check["accuracy"] <= 1
    assert "reliable" in check["note"]


def test_confidence_table_is_consistent():
    table = trained_nlp()["metrics"]["confidence_table"]
    assert table[0]["share_suggested"] == 1.0
    shares = [row["share_suggested"] for row in table]
    assert shares == sorted(shares, reverse=True)


def test_coverage_table_on_a_tiny_example():
    rows = coverage_table(["A", "A", "B"], ["A", "B", "B"], np.array([0.9, 0.3, 0.8]), thresholds=(0.0, 0.5))
    assert rows[0] == {"min_confidence": 0.0, "share_suggested": 1.0, "accuracy_when_suggested": 0.6667}
    assert rows[1] == {"min_confidence": 0.5, "share_suggested": 0.6667, "accuracy_when_suggested": 1.0}


def test_synthetic_data_is_declared_everywhere():
    result = trained_nlp()
    assert result["info"]["trained_on_synthetic_data"] is True
    assert "SYNTHETIC" in result["info"]["data_note"]
    assert result["artifact"]["synthetic"] is True
    assert result["info"]["distinct_templates"] == 19


def test_top_terms_are_listed_for_every_category():
    assert set(trained_nlp()["info"]["top_terms"]) == set(LABELS)


# ---------- saving ----------

def test_artifact_round_trip(tmp_path):
    artifact = trained_nlp()["artifact"]
    loaded = load_artifact(save_artifact(artifact, tmp_path / "nlp" / "model.joblib"))
    assert classify(artifact, STALKING) == classify(loaded, STALKING)


def test_load_rejects_foreign_files(tmp_path):
    path = tmp_path / "other.joblib"
    joblib.dump({"hello": "world"}, path)
    with pytest.raises(ValueError):
        load_artifact(path)


def test_metrics_and_charts_are_written(tmp_path):
    result = trained_nlp()
    assert "SYNTHETIC" in save_metrics(result, tmp_path / "m.json").read_text(encoding="utf-8")
    charts = save_charts(result, tmp_path)
    assert len(charts) == 2 and all(p.exists() and p.stat().st_size > 1000 for p in charts)


# ---------- using the model ----------

def test_suggests_a_category_for_clear_text():
    artifact = trained_nlp()["artifact"]
    result = classify(artifact, STALKING)
    assert result["status"] == "suggested"
    assert result["category"] == "Stalking"
    assert 0.5 <= result["confidence"] <= 1
    assert classify(artifact, UNSAFE)["category"] == "Unsafe surroundings"


def test_result_never_contains_the_text():
    result = classify(trained_nlp()["artifact"], STALKING)
    assert STALKING not in str(result)
    assert set(result) == {"status", "category", "confidence", "message", "synthetic", "disclaimer"}


@pytest.mark.parametrize("text", [
    "", "   ", None, 12345, "xyzzy qwerty zzzz", "ok",
    "ನನ್ನನ್ನು ಹಿಂಬಾಲಿಸಿದರು",                         # Kannada: words the model does not know
    "mujhe koi peecha kar raha tha",                  # Hindi in English letters
])
def test_unknown_or_unusable_text_is_uncertain_not_guessed(text):
    result = classify(trained_nlp()["artifact"], text)
    assert result["status"] == "uncertain"
    assert result["category"] is None


def test_a_high_bar_leaves_the_category_empty():
    result = classify(trained_nlp()["artifact"], STALKING, min_confidence=0.999)
    assert result["status"] == "uncertain"
    assert result["category"] is None
    assert result["confidence"] is not None