"""Turns cleaned incidents into the table the risk model learns from.

The idea, in plain words
------------------------
* The study area is cut into a grid of small squares called CELLS (about 550 m).
* A day is cut into four TIME SLOTS (morning, afternoon, evening, night), and into
  weekday or weekend.
* For every (cell, slot, weekday/weekend) we add up the severity of the reported
  incidents and divide by the number of days: a "risk score" per day.
* The scores are turned into three levels, Low / Moderate / High, using cut-offs taken
  from the TRAINING period only. The levels are RELATIVE: they compare places and times
  with each other inside the data. "Low" never means "safe".
* Only cells with enough reports are modelled. Every other cell is UNKNOWN.

Honest evaluation
-----------------
The data is split by TIME. The model learns from the earlier part and is tested on the
later part, which it has never seen, like a real forecast.
"""
import numpy as np
import pandas as pd

from app.ml.zones import CENTER_LAT, CENTER_LON, STUDY_AREA_RADIUS_DEG

GRID_SIZE_DEG = 0.005                     # about 550 m
ORIGIN_LAT = CENTER_LAT - STUDY_AREA_RADIUS_DEG
ORIGIN_LON = CENTER_LON - STUDY_AREA_RADIUS_DEG
N_CELLS = int(round(2 * STUDY_AREA_RADIUS_DEG / GRID_SIZE_DEG))

RISK_LEVELS = ("Low", "Moderate", "High")
SLOT_NAMES = ("Morning", "Afternoon", "Evening", "Night")
SLOT_HOURS = ("05:00 to 11:59", "12:00 to 16:59", "17:00 to 20:59", "21:00 to 04:59")

MIN_CELL_REPORTS = 8        # fewer reports than this in the training period -> UNKNOWN
TEST_FRACTION = 0.25        # the latest quarter of the period is kept for testing
MIN_PERIOD_DAYS = 14

FEATURE_NAMES = ["cell_lat", "cell_lon", "slot", "is_weekend", "cell_reports", "nearby_reports"]


def slot_of_hour(hour):
    """0 morning, 1 afternoon, 2 evening, 3 night."""
    if 5 <= hour <= 11:
        return 0
    if 12 <= hour <= 16:
        return 1
    if 17 <= hour <= 20:
        return 2
    return 3


def cell_of(lat, lon):
    """(row, col) of the grid cell holding a point, or None if outside the study area."""
    row = int(np.floor((lat - ORIGIN_LAT) / GRID_SIZE_DEG))
    col = int(np.floor((lon - ORIGIN_LON) / GRID_SIZE_DEG))
    if 0 <= row < N_CELLS and 0 <= col < N_CELLS:
        return row, col
    return None


def cell_id(row, col):
    return f"{row}_{col}"


def cell_center(row, col):
    return (ORIGIN_LAT + (row + 0.5) * GRID_SIZE_DEG, ORIGIN_LON + (col + 0.5) * GRID_SIZE_DEG)


def label_scores(scores, low_cut, high_cut):
    """Score per day -> Low / Moderate / High using the cut-offs."""
    scores = np.asarray(scores, dtype=float)
    return np.select([scores <= low_cut, scores <= high_cut], ["Low", "Moderate"], default="High")


def add_cell_columns(df):
    """Adds row, col, cell_id, slot and is_weekend (0 or 1) to a copy of the incidents."""
    out = df.copy()
    out["row"] = np.floor((out["latitude"] - ORIGIN_LAT) / GRID_SIZE_DEG).astype(int)
    out["col"] = np.floor((out["longitude"] - ORIGIN_LON) / GRID_SIZE_DEG).astype(int)
    out["cell_id"] = out["row"].astype(str) + "_" + out["col"].astype(str)
    out["slot"] = out["incident_time"].dt.hour.map(slot_of_hour).astype(int)
    out["is_weekend"] = (out["incident_time"].dt.day_of_week >= 5).astype(int)
    return out


def _day_counts(start, end_exclusive):
    days = pd.date_range(start, end_exclusive - pd.Timedelta(days=1), freq="D")
    weekend = int((days.day_of_week >= 5).sum())
    return {0: len(days) - weekend, 1: weekend}


def _score_table(incidents, cell_ids, days):
    """One row for every cell x slot x weekday/weekend, including those with no reports."""
    grid = pd.MultiIndex.from_product(
        [cell_ids, range(len(SLOT_NAMES)), (0, 1)], names=["cell_id", "slot", "is_weekend"]
    ).to_frame(index=False)
    found = (incidents[incidents["cell_id"].isin(cell_ids)]
             .groupby(["cell_id", "slot", "is_weekend"])
             .agg(incidents=("severity", "size"), severity_sum=("severity", "sum"))
             .reset_index())
    table = grid.merge(found, how="left", on=["cell_id", "slot", "is_weekend"])
    table[["incidents", "severity_sum"]] = table[["incidents", "severity_sum"]].fillna(0)
    table["risk_score"] = table["severity_sum"] / table["is_weekend"].map(days)
    return table


def build_risk_tables(df, test_fraction=TEST_FRACTION, min_cell_reports=MIN_CELL_REPORTS):
    """Build the training and test tables from cleaned incidents.

    Returns a dict with: train, test (tables with features and a 'level' label),
    thresholds, profile (what is known about each modelled cell), cutoff and period info.
    Raises ValueError when there is too little data to do this honestly.
    """
    if df.empty:
        raise ValueError("There are no incidents to learn from.")

    data = add_cell_columns(df)
    first_day = data["incident_time"].min().normalize()
    last_day = data["incident_time"].max().normalize()
    span = (last_day - first_day).days + 1
    cutoff = first_day + pd.Timedelta(days=int(span * (1 - test_fraction)))
    train_days = (cutoff - first_day).days
    test_days = (last_day + pd.Timedelta(days=1) - cutoff).days
    if train_days < MIN_PERIOD_DAYS or test_days < MIN_PERIOD_DAYS:
        raise ValueError(f"Need at least {MIN_PERIOD_DAYS} days in both the training and test periods.")

    train_inc = data[data["incident_time"] < cutoff]
    test_inc = data[data["incident_time"] >= cutoff]

    # What the model is allowed to know about each place: reports in the TRAINING period only.
    counts = train_inc.groupby(["row", "col"]).size()
    lookup = counts.to_dict()
    modelled = counts[counts >= min_cell_reports]
    if modelled.empty:
        raise ValueError("No grid cell has enough reports to model.")

    profile = {}
    for (row, col), reports in modelled.items():
        nearby = sum(lookup.get((row + dr, col + dc), 0) for dr in (-1, 0, 1) for dc in (-1, 0, 1))
        lat, lon = cell_center(row, col)
        profile[cell_id(row, col)] = {
            "row": int(row), "col": int(col), "cell_lat": lat, "cell_lon": lon,
            "cell_reports": int(reports), "nearby_reports": int(nearby),
        }
    cell_ids = sorted(profile)
    profile_df = pd.DataFrame.from_dict(profile, orient="index").rename_axis("cell_id").reset_index()
    profile_df = profile_df[["cell_id", "cell_lat", "cell_lon", "cell_reports", "nearby_reports"]]

    train = _score_table(train_inc, cell_ids, _day_counts(first_day, cutoff))
    test = _score_table(test_inc, cell_ids, _day_counts(cutoff, last_day + pd.Timedelta(days=1)))

    # Cut-offs come from the training period only, then are applied unchanged to the test period.
    low_cut, high_cut = (float(v) for v in np.quantile(train["risk_score"], [1 / 3, 2 / 3]))
    if not low_cut < high_cut:
        raise ValueError("Risk scores do not vary enough to form three levels. Use more data.")

    for table in (train, test):
        table["level"] = label_scores(table["risk_score"], low_cut, high_cut)
    train = train.merge(profile_df, on="cell_id")
    test = test.merge(profile_df, on="cell_id")

    return {
        "train": train,
        "test": test,
        "thresholds": {"low_cut": low_cut, "high_cut": high_cut},
        "profile": profile,
        "cutoff": cutoff,
        "first_day": first_day,
        "last_day": last_day,
        "train_incidents": int(len(train_inc)),
        "test_incidents": int(len(test_inc)),
    }