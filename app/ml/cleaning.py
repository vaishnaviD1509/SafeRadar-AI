"""Cleans a raw incident table and explains exactly what was changed or removed.

Rules:
  * Rows that cannot be repaired safely are DROPPED and counted. Nothing is guessed
    or filled in (for example, a missing severity is never replaced by an average).
  * Only harmless fixes are applied: extra spaces and capital letters.
  * Every step is counted in the returned report, so nothing disappears silently.
"""
import re
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.config import Config
from app.ml.zones import CATEGORIES, CENTER_LAT, CENTER_LON, STUDY_AREA_RADIUS_DEG

REQUIRED_COLUMNS = [
    "description", "category", "severity", "latitude", "longitude", "incident_time", "is_synthetic",
]

CLEAN_COLUMNS = [
    "report_id", "description", "category", "severity", "latitude", "longitude",
    "zone", "area_type", "incident_time", "date", "hour", "day_of_week", "day_name",
    "month", "is_weekend", "is_night", "is_synthetic",
]

TIME_FORMAT = "%Y-%m-%d %H:%M"
MIN_DESCRIPTION = 20     # same limits as the report form
MAX_DESCRIPTION = 2000

_CANONICAL = {name.lower(): name for name in CATEGORIES}


def local_now():
    offset = timedelta(minutes=Config.LOCAL_UTC_OFFSET_MINUTES)
    return (datetime.now(timezone.utc) + offset).replace(tzinfo=None)


def _clean_text(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _canonical_category(value):
    if not isinstance(value, str):
        return None
    return _CANONICAL.get(value.strip().lower())


def _to_bool(value):
    return str(value).strip().lower() in ("true", "1", "yes")


def _drop(df, keep, reason, dropped):
    dropped[reason] = int((~keep).sum())
    return df[keep].copy()


def clean_incidents(raw, reference_time=None):
    """Return (clean_dataframe, report_dict). The input table is not changed."""
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing_cols:
        raise ValueError(f"The data is missing required columns: {', '.join(missing_cols)}")

    reference_time = reference_time or local_now()
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for optional in ("report_id", "zone", "area_type"):
        if optional not in df.columns:
            df[optional] = ""

    rows_in = len(df)
    missing_before = {c: int(df[c].isna().sum()) for c in REQUIRED_COLUMNS}
    dropped, fixed = {}, {}

    # 1. Description: tidy spaces, then drop if absent or outside the allowed length.
    df["description"] = df["description"].map(_clean_text)
    length = df["description"].str.len()
    df = _drop(df, (length >= MIN_DESCRIPTION) & (length <= MAX_DESCRIPTION),
               "missing_or_invalid_description", dropped)

    # 2. Category: fix capital letters and spaces, drop labels the system does not know.
    original = df["category"]
    canonical = original.map(_canonical_category)
    fixed["category_text_fixed"] = int(((canonical.notna()) & (canonical != original)).sum())
    df["category"] = canonical
    df = _drop(df, df["category"].notna(), "missing_or_unknown_category", dropped)

    # 3. Coordinates must be real numbers.
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    valid_numbers = np.isfinite(df["latitude"]) & np.isfinite(df["longitude"])
    df = _drop(df, valid_numbers, "missing_or_invalid_coordinates", dropped)

    # 4. ...and inside the study area (removes 0,0 and swapped latitude/longitude).
    inside = ((df["latitude"] - CENTER_LAT).abs() <= STUDY_AREA_RADIUS_DEG) & \
             ((df["longitude"] - CENTER_LON).abs() <= STUDY_AREA_RADIUS_DEG)
    df = _drop(df, inside, "outside_study_area", dropped)

    # 5. Severity must be a whole number from 1 to 5. Missing values are NOT filled in.
    severity = pd.to_numeric(df["severity"], errors="coerce")
    valid_severity = severity.between(1, 5) & (severity == severity.round())
    df["severity"] = severity
    df = _drop(df, valid_severity, "invalid_severity", dropped)
    df["severity"] = df["severity"].astype(int)

    # 6. Time must be readable and not in the future.
    df["incident_time"] = pd.to_datetime(df["incident_time"], format=TIME_FORMAT, errors="coerce")
    df = _drop(df, df["incident_time"].notna() & (df["incident_time"] <= reference_time),
               "invalid_or_future_time", dropped)

    # 7. Exact repeats (same text, place and time) are counted once.
    key = df["description"].str.lower()
    duplicate = df.assign(_key=key).duplicated(
        subset=["_key", "latitude", "longitude", "incident_time"], keep="first")
    df = _drop(df, ~duplicate, "duplicate", dropped)

    # Everything left must be labelled synthetic or real; the flag is kept, never guessed.
    df["is_synthetic"] = df["is_synthetic"].map(_to_bool)

    # Features that the next phases use.
    df["date"] = df["incident_time"].dt.strftime("%Y-%m-%d")
    df["hour"] = df["incident_time"].dt.hour
    df["day_of_week"] = df["incident_time"].dt.day_of_week
    df["day_name"] = df["incident_time"].dt.day_name()
    df["month"] = df["incident_time"].dt.month
    df["is_weekend"] = df["day_of_week"] >= 5
    df["is_night"] = (df["hour"] >= 21) | (df["hour"] < 5)

    df = df.sort_values("incident_time").reset_index(drop=True)[CLEAN_COLUMNS]

    report = {
        "rows_in": int(rows_in),
        "rows_out": int(len(df)),
        "rows_dropped": int(rows_in - len(df)),
        "dropped_by_reason": dropped,
        "fixed": fixed,
        "missing_values_before": missing_before,
        "all_rows_synthetic": bool(len(df) > 0 and df["is_synthetic"].all()),
    }
    return df, report