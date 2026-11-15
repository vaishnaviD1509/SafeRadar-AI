import joblib
import numpy as np
import pandas as pd
import pytest

from app.ml.risk_dataset import (
    FEATURE_NAMES, MIN_CELL_REPORTS, N_CELLS, RISK_LEVELS, SLOT_NAMES, add_cell_columns,
    build_risk_tables, cell_center, cell_id, cell_of, label_scores, slot_of_hour,
)
from app.ml.risk_model import (
    load_artifact, predict_risk, save_artifact, save_charts, save_metrics, train_and_evaluate,
)
from app.ml.zones import CENTER_LAT, CENTER_LON
from tests.risk_helpers import clean_data, trained

WHEN_NIGHT = pd.Timestamp("2026-11-20 22:30").to_pydatetime()
WHEN_MORNING = pd.Timestamp("2026-11-20 09:00").to_pydatetime()


# ---------- grid and slots ----------

def test_slot_boundaries():
    expected = {4: 3, 5: 0, 11: 0, 12: 1, 16: 1, 17: 2, 20: 2, 21: 3, 23: 3, 0: 3}
    for hour, slot in expected.items():
        assert slot_of_hour(hour) == slot, hour
    assert len(SLOT_NAMES) == 4


def test_cell_of_and_center_round_trip():
    row, col = cell_of(CENTER_LAT, CENTER_LON)
    lat, lon = cell_center(row, col)
    assert cell_of(lat, lon) == (row, col)
    assert abs(lat - CENTER_LAT) < 0.005 and abs(lon - CENTER_LON) < 0.005
    assert 0 <= row < N_CELLS and 0 <= col < N_CELLS


def test_points_outside_the_study_area_have_no_cell():
    assert cell_of(20.0, 80.0) is None
    assert cell_of(0.0, 0.0) is None


def test_label_scores_uses_cutoffs():
    labels = label_scores([0.0, 0.05, 0.2], low_cut=0.1, high_cut=0.15)
    assert list(labels) == ["Low", "Low", "High"]
    assert list(label_scores([0.12], 0.1, 0.15)) == ["Moderate"]


# ---------- tables ----------

@pytest.fixture(scope="module")
def tables():
    return build_risk_tables(clean_data())


def test_split_is_by_time_and_loses_nothing(tables):
    df = clean_data()
    assert tables["train_incidents"] + tables["test_incidents"] == len(df)
    assert tables["first_day"] < tables["cutoff"] <= tables["last_day"]


def test_tables_are_complete_and_valid(tables):
    for name in ("train", "test"):
        table = tables[name]
        assert set(table["level"]) <= set(RISK_LEVELS)
        assert not table[FEATURE_NAMES].isna().any().any()
        # every modelled cell appears with all 4 slots x weekday/weekend, even with zero reports
        assert len(table) == len(tables["profile"]) * len(SLOT_NAMES) * 2
        assert (table["risk_score"] >= 0).all()
    assert tables["thresholds"]["low_cut"] < tables["thresholds"]["high_cut"]


def test_only_cells_with_enough_reports_are_modelled(tables):
    assert all(entry["cell_reports"] >= MIN_CELL_REPORTS for entry in tables["profile"].values())


def test_cell_profile_uses_the_training_period_only(tables):
    """No peeking at the test period: reports per cell are counted before the cutoff."""
    data = add_cell_columns(clean_data())
    train = data[data["incident_time"] < tables["cutoff"]]
    counts = train.groupby("cell_id").size()
    for cid, entry in tables["profile"].items():
        assert entry["cell_reports"] == counts[cid]


def test_thresholds_come_from_training_scores(tables):
    train_scores = tables["train"]["risk_score"]
    low, high = np.quantile(train_scores, [1 / 3, 2 / 3])
    assert tables["thresholds"]["low_cut"] == pytest.approx(low)
    assert tables["thresholds"]["high_cut"] == pytest.approx(high)


def test_too_little_data_raises():
    with pytest.raises(ValueError):
        build_risk_tables(clean_data().iloc[0:0])
    data = clean_data()
    one_week = data[data["incident_time"] < data["incident_time"].min() + pd.Timedelta(days=7)]
    with pytest.raises(ValueError, match="at least"):
        build_risk_tables(one_week)
    with pytest.raises(ValueError, match="enough reports"):
        build_risk_tables(clean_data(), min_cell_reports=10_000)


# ---------- training and honest metrics ----------

def test_metrics_are_measured_and_add_up():
    result = trained()
    info, metrics = result["info"], result["metrics"]
    assert set(metrics) == {"majority_baseline", "persistence_baseline", "decision_tree", "random_forest"}
    for name, m in metrics.items():
        matrix = np.array(m["confusion_matrix"])
        assert matrix.sum() == info["test_rows"], name
        assert sum(level["support"] for level in m["per_level"].values()) == info["test_rows"], name
        assert 0 <= m["accuracy"] <= 1 and 0 <= m["macro_f1"] <= 1
        assert m["accuracy"] == pytest.approx(np.trace(matrix) / matrix.sum(), abs=1e-4)


def test_random_forest_beats_a_blind_guess_on_macro_f1():
    metrics = trained()["metrics"]
    assert metrics["random_forest"]["macro_f1"] > metrics["majority_baseline"]["macro_f1"]


def test_synthetic_data_is_declared_everywhere():
    result = trained()
    assert result["info"]["trained_on_synthetic_data"] is True
    assert "SYNTHETIC" in result["info"]["data_note"]
    assert result["artifact"]["synthetic"] is True
    assert result["info"]["cutoff_date"] > result["info"]["period_from"]


def test_training_is_repeatable():
    first = trained()["metrics"]
    second = train_and_evaluate(clean_data())["metrics"]
    assert first == second


def test_feature_importance_covers_every_feature():
    importance = trained()["info"]["feature_importance"]
    assert set(importance) == set(FEATURE_NAMES)
    assert sum(importance.values()) == pytest.approx(1.0, abs=0.01)


# ---------- saving and loading ----------

def test_artifact_round_trip(tmp_path):
    artifact = trained()["artifact"]
    path = save_artifact(artifact, tmp_path / "model" / "risk.joblib")
    loaded = load_artifact(path)
    cell = next(iter(artifact["profile"].values()))
    a = predict_risk(artifact, cell["cell_lat"], cell["cell_lon"], WHEN_NIGHT)
    b = predict_risk(loaded, cell["cell_lat"], cell["cell_lon"], WHEN_NIGHT)
    assert a == b


def test_load_rejects_foreign_files(tmp_path):
    path = tmp_path / "other.joblib"
    joblib.dump({"hello": "world"}, path)
    with pytest.raises(ValueError):
        load_artifact(path)


def test_metrics_and_charts_are_written(tmp_path):
    result = trained()
    metrics_file = save_metrics(result, tmp_path / "metrics.json")
    assert "SYNTHETIC" in metrics_file.read_text(encoding="utf-8")
    charts = save_charts(result, tmp_path)
    assert len(charts) == 2 and all(p.exists() and p.stat().st_size > 1000 for p in charts)


# ---------- predictions ----------

def _modelled_cell():
    return next(iter(trained()["artifact"]["profile"].values()))


def test_estimate_for_a_modelled_place():
    cell = _modelled_cell()
    result = predict_risk(trained()["artifact"], cell["cell_lat"], cell["cell_lon"], WHEN_NIGHT)
    assert result["status"] == "estimate"
    assert result["level"] in RISK_LEVELS
    assert result["slot"] == "Night"
    assert sum(result["probabilities"].values()) == pytest.approx(1.0, abs=0.01)
    assert result["synthetic"] is True
    assert "not a guarantee" in result["disclaimer"]


def test_slot_follows_the_time_of_day():
    cell = _modelled_cell()
    artifact = trained()["artifact"]
    assert predict_risk(artifact, cell["cell_lat"], cell["cell_lon"], WHEN_MORNING)["slot"] == "Morning"


def test_unknown_places_are_never_called_low():
    artifact = trained()["artifact"]
    inside_but_empty = predict_risk(artifact, CENTER_LAT + 0.2, CENTER_LON + 0.2, WHEN_NIGHT)
    outside = predict_risk(artifact, 20.0, 80.0, WHEN_NIGHT)
    for result in (inside_but_empty, outside):
        assert result["status"] == "unknown"
        assert result["level"] is None
        assert result["probabilities"] is None
    assert "outside" in outside["message"]
    assert "not enough reports" in inside_but_empty["message"]