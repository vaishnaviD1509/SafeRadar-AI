"""Trains, evaluates, saves and uses the risk prediction model.

Models
------
* Decision Tree  - a simple, easy-to-explain baseline.
* Random Forest  - the main model (many trees voting). This is the one that is saved
                   and used by the web app.
Two "no learning" baselines are reported too, so the models are judged fairly:
* majority   - always guess the most common level in the training data
* persistence - guess that a place and time keeps the level it had in the training period

Every number printed or saved is MEASURED on the held-out later period. When the data
is synthetic, the metrics are labelled so: they show how well the model recovers the
patterns written into the generator, not how well it predicts real-world safety.
"""
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.tree import DecisionTreeClassifier

from app.ml.risk_dataset import (
    FEATURE_NAMES, GRID_SIZE_DEG, MIN_CELL_REPORTS, RISK_LEVELS, SLOT_HOURS, SLOT_NAMES,
    build_risk_tables, cell_id, cell_of, slot_of_hour,
)

ARTIFACT_VERSION = 1
SEED = 42
PURPLE, NAVY, PINK = "#6d28d9", "#0f1b3d", "#f9a8d4"

DISCLAIMER = (
    "A model estimate, not a guarantee of safety. Levels compare places and times within "
    "the data the model learned from. A place with few or no reports is unknown, not safe."
)


def make_decision_tree():
    return DecisionTreeClassifier(max_depth=6, min_samples_leaf=5, class_weight="balanced",
                                  random_state=SEED)


def make_random_forest():
    return RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=3,
                                  class_weight="balanced", random_state=SEED, n_jobs=1)


def evaluate(y_true, y_pred):
    """Accuracy, macro F1, per-level precision/recall/F1 and the confusion matrix."""
    levels = list(RISK_LEVELS)
    report = classification_report(y_true, y_pred, labels=levels, output_dict=True, zero_division=0)
    matrix = confusion_matrix(y_true, y_pred, labels=levels)
    rank = {level: i for i, level in enumerate(levels)}
    gap = np.abs(np.array([rank[v] for v in y_true]) - np.array([rank[v] for v in y_pred]))
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, labels=levels, average="macro", zero_division=0)), 4),
        "within_one_level": round(float((gap <= 1).mean()), 4),
        "per_level": {
            level: {
                "precision": round(float(report[level]["precision"]), 4),
                "recall": round(float(report[level]["recall"]), 4),
                "f1": round(float(report[level]["f1-score"]), 4),
                "support": int(report[level]["support"]),
            }
            for level in levels
        },
        "confusion_matrix": matrix.tolist(),
    }


def train_and_evaluate(df):
    """Train both models on the earlier period and test them on the later period.

    `df` is the cleaned incident table. Returns a dict with the metrics and the
    artifact (everything the web app needs) for the Random Forest.
    """
    tables = build_risk_tables(df)
    train, test = tables["train"], tables["test"]
    x_train, y_train = train[FEATURE_NAMES], train["level"]
    x_test, y_test = test[FEATURE_NAMES], test["level"]

    # Baselines that do no learning
    majority_level = y_train.value_counts().idxmax()
    majority_pred = [majority_level] * len(test)
    earlier = train.set_index(["cell_id", "slot", "is_weekend"])["level"]
    persistence_pred = [
        earlier.get((c, s, w), majority_level)
        for c, s, w in zip(test["cell_id"], test["slot"], test["is_weekend"])
    ]

    tree = make_decision_tree().fit(x_train, y_train)
    forest = make_random_forest().fit(x_train, y_train)

    metrics = {
        "majority_baseline": evaluate(y_test, majority_pred),
        "persistence_baseline": evaluate(y_test, persistence_pred),
        "decision_tree": evaluate(y_test, tree.predict(x_test)),
        "random_forest": evaluate(y_test, forest.predict(x_test)),
    }
    importance = dict(sorted(
        ((name, round(float(v), 4)) for name, v in zip(FEATURE_NAMES, forest.feature_importances_)),
        key=lambda item: item[1], reverse=True))

    synthetic = bool(df["is_synthetic"].all())
    info = {
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "trained_on_synthetic_data": synthetic,
        "data_note": ("Trained and tested on SYNTHETIC data. Metrics show how well the model "
                      "recovers patterns written into the generator, not real-world accuracy.")
                     if synthetic else "Trained on real reported incidents.",
        "incidents_total": int(len(df)),
        "incidents_train_period": tables["train_incidents"],
        "incidents_test_period": tables["test_incidents"],
        "period_from": str(tables["first_day"].date()),
        "cutoff_date": str(tables["cutoff"].date()),
        "period_to": str(tables["last_day"].date()),
        "modelled_cells": len(tables["profile"]),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "thresholds_score_per_day": tables["thresholds"],
        "grid_size_deg": GRID_SIZE_DEG,
        "min_cell_reports": MIN_CELL_REPORTS,
        "test_level_counts": {k: int(v) for k, v in y_test.value_counts().items()},
        "feature_importance": importance,
        "sklearn_version": sklearn.__version__,
        "model_choice": ("Random Forest is the main model, chosen before testing. "
                         "It is trained on the earlier period only, so the metrics describe "
                         "exactly the model the app uses."),
    }
    artifact = {
        "version": ARTIFACT_VERSION,
        "model": forest,
        "feature_names": list(FEATURE_NAMES),
        "levels": list(RISK_LEVELS),
        "thresholds": tables["thresholds"],
        "profile": tables["profile"],
        "synthetic": synthetic,
        "info": info,
    }
    return {"metrics": metrics, "info": info, "artifact": artifact}


# ---------- saving and loading ----------

def save_artifact(artifact, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)
    return path


def load_artifact(path):
    """Load a saved model. Only load files this project created: joblib files can run code."""
    artifact = joblib.load(path)
    if not isinstance(artifact, dict) or artifact.get("version") != ARTIFACT_VERSION:
        raise ValueError("This is not a risk model file from this version of SafeRadar AI.")
    return artifact


def save_metrics(result, path):
    import json

    payload = {"info": result["info"], "metrics": result["metrics"]}
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return Path(path)


# ---------- using the model ----------

def predict_risk(artifact, lat, lon, when_local):
    """Estimate the risk level for a place and a local time.

    Returns a dict. status is 'estimate' or 'unknown'. UNKNOWN means the model has too
    little data for that place; it is never turned into 'Low' or 'safe'.
    """
    slot = slot_of_hour(when_local.hour)
    base = {
        "slot": SLOT_NAMES[slot],
        "slot_hours": SLOT_HOURS[slot],
        "synthetic": bool(artifact["synthetic"]),
        "disclaimer": DISCLAIMER,
    }

    cell = cell_of(lat, lon)
    if cell is None:
        return {**base, "status": "unknown", "level": None, "probabilities": None,
                "message": "This place is outside the area the model covers."}

    entry = artifact["profile"].get(cell_id(*cell))
    if entry is None:
        return {**base, "status": "unknown", "level": None, "probabilities": None,
                "message": "There are not enough reports near this place to give an estimate."}

    features = pd.DataFrame([{
        "cell_lat": entry["cell_lat"], "cell_lon": entry["cell_lon"], "slot": slot,
        "is_weekend": int(when_local.weekday() >= 5),
        "cell_reports": entry["cell_reports"], "nearby_reports": entry["nearby_reports"],
    }])[artifact["feature_names"]]

    model = artifact["model"]
    probabilities = model.predict_proba(features)[0]
    by_level = {str(c): round(float(p), 3) for c, p in zip(model.classes_, probabilities)}
    level = str(model.classes_[int(np.argmax(probabilities))])
    return {**base, "status": "estimate", "level": level, "probabilities": by_level,
            "message": "Estimate from the Random Forest model."}


# ---------- charts ----------

def save_charts(result, out_dir):
    """Confusion matrix and feature importance of the Random Forest."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = " (synthetic demo data)" if result["info"]["trained_on_synthetic_data"] else ""
    paths = []

    matrix = np.array(result["metrics"]["random_forest"]["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(5, 4.2))
    image = ax.imshow(matrix, cmap="Purples")
    ax.set_xticks(range(3), RISK_LEVELS)
    ax.set_yticks(range(3), RISK_LEVELS)
    ax.set_xlabel("Predicted level")
    ax.set_ylabel("Actual level (test period)")
    for i in range(3):
        for j in range(3):
            ax.text(j, i, int(matrix[i, j]), ha="center", va="center",
                    color="white" if matrix[i, j] > matrix.max() / 2 else NAVY)
    fig.colorbar(image, ax=ax)
    ax.set_title(f"Random Forest confusion matrix{tag}", fontsize=11, color=NAVY, loc="left", fontweight="bold")
    fig.tight_layout()
    path = out_dir / "risk_confusion_matrix.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths.append(path)

    importance = result["info"]["feature_importance"]
    names = list(importance)[::-1]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.barh(names, [importance[n] for n in names], color=PURPLE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_xlabel("Importance")
    ax.set_title(f"What the Random Forest relies on{tag}", fontsize=11, color=NAVY, loc="left", fontweight="bold")
    fig.tight_layout()
    path = out_dir / "risk_feature_importance.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths.append(path)
    return paths