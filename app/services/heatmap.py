"""Data for the safety heatmap page.

Two things are drawn on the map:
  * RISK CELLS: the grid squares the risk model knows enough about, coloured Low,
    Moderate or High for a chosen time slot. The levels are RELATIVE (they compare places
    and times inside the training data), so "Low" never means "safe".
  * MARKERS: approved reports, rounded to about 110 m, with no text and no reporter.

A place the model has too little data for is simply not drawn. It is never turned
into "Low": unknown is not safe.
"""
import pandas as pd

from app.ml.risk_dataset import (
    GRID_SIZE_DEG, ORIGIN_LAT, ORIGIN_LON, RISK_LEVELS, SLOT_HOURS, SLOT_NAMES, slot_of_hour,
)
from app.ml.risk_model import DISCLAIMER
from app.services.risk import load_model
from app.services.stats import get_map_markers
from app.utils.timeutils import local_now

MARKER_LIMIT = 500


def current_slot_and_day():
    """(slot index, 0 for weekday or 1 for weekend) for the current local time."""
    now = local_now()
    return slot_of_hour(now.hour), int(now.weekday() >= 5)


def get_heatmap_markers():
    return get_map_markers(limit=MARKER_LIMIT)


def build_risk_grid(slot=None, is_weekend=None):
    """Risk level of every modelled cell for a time slot, or None if there is no model.

    Raises ValueError for a slot outside 0 to 3 or a day type other than 0 or 1.
    """
    now_slot, now_weekend = current_slot_and_day()
    slot = now_slot if slot is None else slot
    is_weekend = now_weekend if is_weekend is None else is_weekend
    if slot not in range(len(SLOT_NAMES)):
        raise ValueError("slot must be 0, 1, 2 or 3.")
    if is_weekend not in (0, 1):
        raise ValueError("weekend must be 0 or 1.")
    slot, is_weekend = int(slot), int(is_weekend)

    artifact = load_model()
    if artifact is None:
        return None

    profile = artifact["profile"]
    ids = sorted(profile)
    counts = {level: 0 for level in RISK_LEVELS}
    cells = []

    if ids:
        features = pd.DataFrame([{
            "cell_lat": profile[cid]["cell_lat"],
            "cell_lon": profile[cid]["cell_lon"],
            "slot": slot,
            "is_weekend": is_weekend,
            "cell_reports": profile[cid]["cell_reports"],
            "nearby_reports": profile[cid]["nearby_reports"],
        } for cid in ids])[artifact["feature_names"]]

        model = artifact["model"]
        classes = [str(c) for c in model.classes_]
        for cid, probabilities in zip(ids, model.predict_proba(features)):
            level = classes[int(probabilities.argmax())]
            counts[level] = counts.get(level, 0) + 1
            entry = profile[cid]
            south = ORIGIN_LAT + entry["row"] * GRID_SIZE_DEG
            west = ORIGIN_LON + entry["col"] * GRID_SIZE_DEG
            cells.append({
                "id": cid,
                "south": round(south, 5),
                "west": round(west, 5),
                "north": round(south + GRID_SIZE_DEG, 5),
                "east": round(west + GRID_SIZE_DEG, 5),
                "level": level,
                "probabilities": {c: round(float(p), 3) for c, p in zip(classes, probabilities)},
            })

    return {
        "status": "ok",
        "slot": SLOT_NAMES[slot],
        "slot_index": slot,
        "slot_hours": SLOT_HOURS[slot],
        "is_weekend": bool(is_weekend),
        "synthetic": bool(artifact["synthetic"]),
        "disclaimer": DISCLAIMER,
        "counts": counts,
        "cells": cells,
    }