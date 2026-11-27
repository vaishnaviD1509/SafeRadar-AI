import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.ml.cleaning import CLEAN_COLUMNS, clean_incidents
from app.ml.eda import build_summary, load_clean, make_charts, write_summary_markdown
from app.ml.synthetic import add_realistic_mess, generate_synthetic_incidents
from app.ml.zones import (
    CATEGORIES, CENTER_LAT, CENTER_LON, DEMO_ZONES, STUDY_AREA_RADIUS_DEG,
)
from scripts import prepare_data, run_eda

END = date(2026, 11, 1)


@pytest.fixture(scope="module")
def generated():
    return generate_synthetic_incidents(n_rows=600, seed=1, days=200, end_date=END)


@pytest.fixture(scope="module")
def raw(generated):
    return add_realistic_mess(generated, seed=2, end_date=END)


@pytest.fixture(scope="module")
def cleaned(raw):
    clean, report = clean_incidents(raw, reference_time=pd.Timestamp("2026-11-01 23:59"))
    return clean, report


# ---------- generator ----------

def test_zone_weights_add_up():
    assert sum(z["weight"] for z in DEMO_ZONES) == pytest.approx(1.0)
    for zone in DEMO_ZONES:
        assert len(zone["category_weights"]) == len(CATEGORIES)


def test_generator_is_repeatable(generated):
    again = generate_synthetic_incidents(n_rows=600, seed=1, days=200, end_date=END)
    pd.testing.assert_frame_equal(generated, again)
    other = generate_synthetic_incidents(n_rows=600, seed=99, days=200, end_date=END)
    assert not generated["description"].equals(other["description"])


def test_generated_rows_are_valid_and_labelled_synthetic(generated):
    assert len(generated) == 600
    assert generated["is_synthetic"].all()
    assert set(generated["category"]) <= set(CATEGORIES)
    assert generated["severity"].between(1, 5).all()
    assert generated["description"].str.len().ge(20).all()
    assert (generated["latitude"] - CENTER_LAT).abs().max() < STUDY_AREA_RADIUS_DEG
    assert (generated["longitude"] - CENTER_LON).abs().max() < STUDY_AREA_RADIUS_DEG
    assert generated["zone"].str.startswith("Demo Zone").all()   # never real place names


def test_generated_times_are_in_the_past(generated):
    times = pd.to_datetime(generated["incident_time"])
    assert times.max() < pd.Timestamp(END)
    assert times.min() >= pd.Timestamp(END) - pd.Timedelta(days=200)


def test_generator_rejects_bad_sizes():
    with pytest.raises(ValueError):
        generate_synthetic_incidents(n_rows=0)


def test_night_zone_has_more_night_incidents():
    df = generate_synthetic_incidents(n_rows=4000, seed=3, days=200, end_date=END)
    hour = pd.to_datetime(df["incident_time"]).dt.hour
    night = (hour >= 21) | (hour < 5)
    outskirts = night[df["zone"].str.contains("Ring road")].mean()
    college = night[df["zone"].str.contains("College")].mean()
    assert outskirts > college


# ---------- mess ----------

def test_mess_adds_every_kind_of_defect(generated, raw):
    assert len(raw) > len(generated)                                  # duplicates added
    assert raw["description"].isna().any() or (raw["description"] == "").any()
    assert raw["latitude"].isna().any() and raw["longitude"].isna().any()
    assert (raw["severity"].isin([0, 6, 9]) | raw["severity"].isna()).any()
    assert (raw["category"] == "Other").any()
    assert raw["category"].map(lambda v: v != str(v).strip() or str(v).isupper()).any()
    assert raw["report_id"].astype(str).str.endswith("-copy").any()


def test_mess_does_not_change_the_input(generated):
    before = generated.copy()
    add_realistic_mess(generated, seed=5, end_date=END)
    pd.testing.assert_frame_equal(generated, before)


# ---------- cleaning ----------

def test_clean_output_is_valid(cleaned):
    clean, _ = cleaned
    assert list(clean.columns) == CLEAN_COLUMNS
    assert len(clean) > 0
    assert set(clean["category"]) <= set(CATEGORIES)
    assert clean["severity"].between(1, 5).all()
    assert clean["description"].str.len().between(20, 2000).all()
    assert clean["latitude"].notna().all() and clean["longitude"].notna().all()
    assert ((clean["latitude"] - CENTER_LAT).abs() <= STUDY_AREA_RADIUS_DEG).all()
    assert (clean["incident_time"] <= pd.Timestamp("2026-11-01 23:59")).all()
    assert not clean.duplicated(subset=["description", "latitude", "longitude", "incident_time"]).any()
    assert clean["is_synthetic"].all()


def test_report_adds_up_and_nothing_vanishes_silently(raw, cleaned):
    clean, report = cleaned
    assert report["rows_in"] == len(raw)
    assert report["rows_out"] == len(clean)
    assert report["rows_in"] - report["rows_out"] == sum(report["dropped_by_reason"].values())
    for reason in ("missing_or_invalid_description", "missing_or_unknown_category",
                   "missing_or_invalid_coordinates", "outside_study_area",
                   "invalid_severity", "invalid_or_future_time", "duplicate"):
        assert report["dropped_by_reason"][reason] > 0, reason
    assert report["fixed"]["category_text_fixed"] > 0
    assert report["all_rows_synthetic"] is True


def test_category_text_is_repaired_not_dropped():
    raw = pd.DataFrame([{
        "description": "A man followed me home from the bus stand last night.",
        "category": "  stalking ", "severity": 3, "latitude": CENTER_LAT, "longitude": CENTER_LON,
        "incident_time": "2026-05-01 20:00", "is_synthetic": True,
    }])
    clean, report = clean_incidents(raw, reference_time=pd.Timestamp("2026-06-01"))
    assert list(clean["category"]) == ["Stalking"]
    assert report["fixed"]["category_text_fixed"] == 1


def test_missing_severity_is_dropped_never_guessed():
    raw = pd.DataFrame([{
        "description": "A man followed me home from the bus stand last night.",
        "category": "Stalking", "severity": np.nan, "latitude": CENTER_LAT, "longitude": CENTER_LON,
        "incident_time": "2026-05-01 20:00", "is_synthetic": True,
    }])
    clean, report = clean_incidents(raw, reference_time=pd.Timestamp("2026-06-01"))
    assert clean.empty
    assert report["dropped_by_reason"]["invalid_severity"] == 1


def test_swapped_and_zero_coordinates_are_removed():
    base = {
        "description": "A man followed me home from the bus stand last night.",
        "category": "Stalking", "severity": 3, "incident_time": "2026-05-01 20:00", "is_synthetic": True,
    }
    raw = pd.DataFrame([
        {**base, "latitude": CENTER_LON, "longitude": CENTER_LAT},   # swapped
        {**base, "latitude": 0.0, "longitude": 0.0},
    ])
    clean, report = clean_incidents(raw, reference_time=pd.Timestamp("2026-06-01"))
    assert clean.empty
    assert report["dropped_by_reason"]["outside_study_area"] == 2


def test_cleaning_twice_changes_nothing(cleaned):
    clean, _ = cleaned
    again_input = clean.copy()
    again_input["incident_time"] = again_input["incident_time"].dt.strftime("%Y-%m-%d %H:%M")
    again, report = clean_incidents(again_input, reference_time=pd.Timestamp("2026-11-01 23:59"))
    assert report["rows_dropped"] == 0
    assert len(again) == len(clean)


def test_cleaning_does_not_change_its_input(raw):
    before = raw.copy()
    clean_incidents(raw, reference_time=pd.Timestamp("2026-11-01 23:59"))
    pd.testing.assert_frame_equal(raw, before)


def test_cleaning_requires_the_synthetic_flag_column(raw):
    with pytest.raises(ValueError, match="is_synthetic"):
        clean_incidents(raw.drop(columns=["is_synthetic"]))


def test_derived_time_features(cleaned):
    clean, _ = cleaned
    row = clean.iloc[0]
    assert row["hour"] == row["incident_time"].hour
    assert row["day_of_week"] == row["incident_time"].day_of_week
    assert row["is_weekend"] == (row["day_of_week"] >= 5)
    night = (clean["hour"] >= 21) | (clean["hour"] < 5)
    assert (clean["is_night"] == night).all()


# ---------- EDA ----------

def test_summary_matches_the_data(cleaned):
    clean, _ = cleaned
    summary = build_summary(clean)
    assert summary["rows"] == len(clean)
    assert sum(summary["category_counts"].values()) == len(clean)
    assert sum(summary["zone_counts"].values()) == len(clean)
    assert sum(summary["severity_counts"].values()) == len(clean)
    assert summary["all_synthetic"] is True


def test_summary_rejects_empty_data(cleaned):
    clean, _ = cleaned
    with pytest.raises(ValueError):
        build_summary(clean.iloc[0:0])


def test_charts_and_markdown_are_written(cleaned, tmp_path):
    clean, _ = cleaned
    charts = make_charts(clean, tmp_path)
    assert len(charts) == 7
    assert all(p.exists() and p.stat().st_size > 1000 for p in charts)
    md = write_summary_markdown(build_summary(clean), charts, tmp_path / "eda_summary.md")
    text = md.read_text(encoding="utf-8")
    assert "SYNTHETIC DATA" in text
    assert "not real events" in text


# ---------- scripts end to end ----------

def test_prepare_and_eda_scripts_work_together(tmp_path):
    raw_path = tmp_path / "raw" / "raw.csv"
    clean_path = tmp_path / "processed" / "clean.csv"
    report_path = tmp_path / "processed" / "report.json"

    report = prepare_data.run(rows=300, seed=4, days=120, raw_path=raw_path,
                              clean_path=clean_path, report_path=report_path)
    assert raw_path.exists() and clean_path.exists() and report_path.exists()
    assert 0 < report["rows_out"] < report["rows_in"]
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert "SYNTHETIC" in saved["note"]

    df = load_clean(clean_path)
    assert len(df) == report["rows_out"]
    assert df["is_synthetic"].all()

    summary, charts = run_eda.run(clean_path=clean_path, out_dir=tmp_path / "eda")
    assert summary["rows"] == len(df)
    assert len(charts) == 7
    assert (tmp_path / "eda" / "eda_summary.md").exists()