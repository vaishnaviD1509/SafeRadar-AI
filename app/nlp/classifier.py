"""Trains, evaluates, saves and uses the incident text classifier.

How it works
------------
1. normalize_text() cleans the description (lowercase, stems, no filler words).
2. TF-IDF turns the words (and word pairs) into numbers: words that are frequent in one
   description but rare overall count for more.
3. Logistic Regression turns those numbers into a probability for each category.
   It is the main model. Naive Bayes is trained alongside as a comparison, and a
   "most common category" guess shows what no learning would score.

The app only SUGGESTS a category. If the model is not confident enough, the report is left
uncategorised for an administrator, and an administrator confirms every report anyway.

Honest evaluation
-----------------
* Grouped cross-validation keeps every sentence template wholly inside either the training
  part or the test part, so the score reflects NEW wording, not memorised sentences.
* A normal random split is also reported, only to show how much higher it is (it is
  inflated, because the same templates appear on both sides).
* 32 hand-written sentences, never used in training, give a rough second opinion.
When the data is synthetic every score is labelled so. None of them is real-world accuracy.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedShuffleSplit
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from app.ml.zones import CATEGORIES
from app.nlp.check_sentences import CHECK_SENTENCES
from app.nlp.groups import template_key
from app.nlp.text import normalize_text

ARTIFACT_VERSION = 1
SEED = 42
N_FOLDS = 5
MIN_CONFIDENCE = 0.50       # below this the category is not suggested (decided before testing)
MIN_KNOWN_WORDS = 2         # fewer known words than this -> "uncertain"
LABELS = sorted(CATEGORIES)

PURPLE, NAVY = "#6d28d9", "#0f1b3d"

DISCLAIMER = ("An automatic suggestion. An administrator checks every report before it is "
              "shown to anyone else.")


# ---------- the models ----------

def _vectorizer():
    return TfidfVectorizer(preprocessor=normalize_text, token_pattern=r"\S+", lowercase=False,
                           ngram_range=(1, 2), sublinear_tf=True)


def make_logistic_regression():
    return Pipeline([
        ("tfidf", _vectorizer()),
        ("model", LogisticRegression(C=5.0, max_iter=2000, class_weight="balanced", random_state=SEED)),
    ])


def make_naive_bayes():
    return Pipeline([("tfidf", _vectorizer()), ("model", MultinomialNB(alpha=0.5))])


# ---------- evaluation helpers ----------

def evaluate(y_true, y_pred):
    report = classification_report(y_true, y_pred, labels=LABELS, output_dict=True, zero_division=0)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)), 4),
        "per_category": {
            label: {
                "precision": round(float(report[label]["precision"]), 4),
                "recall": round(float(report[label]["recall"]), 4),
                "f1": round(float(report[label]["f1-score"]), 4),
                "support": int(report[label]["support"]),
            }
            for label in LABELS
        },
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
    }


def grouped_folds(labels, groups, n_splits=N_FOLDS):
    """(train_index, test_index) pairs where no template is on both sides.

    Each category's templates are spread over the folds, so every test fold holds some
    unseen templates of (almost) every category and every training part still sees each one.
    """
    labels, groups = np.asarray(labels), np.asarray(groups)
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=SEED)
    return list(splitter.split(np.zeros(len(labels)), labels, groups))


def grouped_cross_validation(texts, labels, groups, make_model):
    """Out-of-fold predictions on templates the model never saw while training."""
    texts, labels = np.asarray(texts, dtype=object), np.asarray(labels, dtype=object)
    predicted = np.empty(len(texts), dtype=object)
    confidence = np.zeros(len(texts))
    fold_f1 = []
    for train_idx, test_idx in grouped_folds(labels, groups):
        model = make_model().fit(texts[train_idx], labels[train_idx])
        predicted[test_idx] = model.predict(texts[test_idx])
        if hasattr(model, "predict_proba"):
            confidence[test_idx] = model.predict_proba(texts[test_idx]).max(axis=1)
        present = sorted(set(labels[test_idx]))   # score only categories that are in this fold
        fold_f1.append(f1_score(labels[test_idx], predicted[test_idx], labels=present,
                                average="macro", zero_division=0))
    return predicted, confidence, fold_f1


def random_split_score(texts, labels, make_model):
    """Ordinary random split. Optimistic: the same templates appear in train and test."""
    texts, labels = np.asarray(texts, dtype=object), np.asarray(labels, dtype=object)
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED)
    train_idx, test_idx = next(splitter.split(texts, labels))
    model = make_model().fit(texts[train_idx], labels[train_idx])
    return evaluate(labels[test_idx], model.predict(texts[test_idx]))


def coverage_table(labels, predicted, confidence, thresholds=(0.0, 0.4, 0.5, 0.6, 0.7, 0.8)):
    """For each confidence threshold: how many reports get a suggestion, and how often it is right."""
    labels, predicted = np.asarray(labels, dtype=object), np.asarray(predicted, dtype=object)
    rows = []
    for threshold in thresholds:
        kept = confidence >= threshold
        rows.append({
            "min_confidence": threshold,
            "share_suggested": round(float(kept.mean()), 4),
            "accuracy_when_suggested": round(float((labels[kept] == predicted[kept]).mean()), 4)
                                       if kept.any() else None,
        })
    return rows


# ---------- training ----------

def train_and_evaluate(df):
    """`df` needs the columns description, category and is_synthetic (the cleaned incidents)."""
    texts = df["description"].tolist()
    labels = df["category"].tolist()
    groups = df["description"].map(template_key).tolist()

    majority = max(set(labels), key=labels.count)
    lr_pred, lr_conf, lr_folds = grouped_cross_validation(texts, labels, groups, make_logistic_regression)
    nb_pred, _, nb_folds = grouped_cross_validation(texts, labels, groups, make_naive_bayes)

    cross_validation = {
        "majority_baseline": evaluate(labels, [majority] * len(labels)),
        "naive_bayes": {**evaluate(labels, nb_pred),
                        "fold_macro_f1": [round(float(v), 4) for v in nb_folds]},
        "logistic_regression": {**evaluate(labels, lr_pred),
                                "fold_macro_f1": [round(float(v), 4) for v in lr_folds]},
    }
    random_split = {
        "naive_bayes": random_split_score(texts, labels, make_naive_bayes),
        "logistic_regression": random_split_score(texts, labels, make_logistic_regression),
    }

    # The model the app uses: logistic regression trained on every row.
    final = make_logistic_regression().fit(texts, labels)

    check = evaluate_check_sentences(final)

    synthetic = bool(df["is_synthetic"].all())
    n_templates = len(set(groups))
    info = {
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "trained_on_synthetic_data": synthetic,
        "data_note": ("Trained on SYNTHETIC text built from a small set of sentence templates. "
                      "Scores show how well the model copes with these templates, not how it "
                      "would perform on real reports.")
                     if synthetic else "Trained on real reported incidents.",
        "rows": len(texts),
        "distinct_templates": n_templates,
        "category_counts": {label: labels.count(label) for label in LABELS},
        "vocabulary_size": len(final.named_steps["tfidf"].vocabulary_),
        "min_confidence": MIN_CONFIDENCE,
        "min_known_words": MIN_KNOWN_WORDS,
        "folds": N_FOLDS,
        "sklearn_version": sklearn.__version__,
        "model_choice": ("Logistic Regression is the main model, chosen before testing with fixed "
                         "settings (nothing was tuned on the test data). The cross-validation scores "
                         "describe this same method; the saved model is trained on every row."),
        "top_terms": top_terms(final),
    }
    metrics = {
        "grouped_cross_validation": cross_validation,
        "random_split_inflated": random_split,
        "confidence_table": coverage_table(labels, lr_pred, lr_conf),
        "hand_written_check": check,
    }
    artifact = {
        "version": ARTIFACT_VERSION,
        "pipeline": final,
        "labels": list(final.classes_),
        "min_confidence": MIN_CONFIDENCE,
        "min_known_words": MIN_KNOWN_WORDS,
        "synthetic": synthetic,
        "info": info,
    }
    return {"info": info, "metrics": metrics, "artifact": artifact,
            "out_of_fold": {"labels": labels, "predicted": list(lr_pred)}}


def evaluate_check_sentences(pipeline):
    texts = [text for text, _ in CHECK_SENTENCES]
    truth = [label for _, label in CHECK_SENTENCES]
    predicted = list(pipeline.predict(texts))
    confidence = pipeline.predict_proba(texts).max(axis=1)
    result = evaluate(truth, predicted)
    result["note"] = ("32 hand-written sentences in wording different from the templates. Too few for a "
                      "reliable accuracy; labels are the writer's own reading.")
    result["sentences"] = len(texts)
    result["suggested_at_threshold"] = int((confidence >= MIN_CONFIDENCE).sum())
    result["wrong"] = [
        {"text": text, "truth": t, "predicted": p, "confidence": round(float(c), 3)}
        for text, t, p, c in zip(texts, truth, predicted, confidence) if t != p
    ]
    return result


def top_terms(pipeline, n=8):
    """The stemmed words that push the model most strongly towards each category."""
    words = np.array(pipeline.named_steps["tfidf"].get_feature_names_out())
    coefficients = pipeline.named_steps["model"].coef_
    classes = pipeline.named_steps["model"].classes_
    return {str(label): [str(w) for w in words[np.argsort(row)[::-1][:n]]]
            for label, row in zip(classes, coefficients)}


# ---------- saving and loading ----------

def save_artifact(artifact, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)
    return path


def load_artifact(path):
    """Load a saved classifier. Only load files this project created: joblib files can run code."""
    artifact = joblib.load(path)
    if not isinstance(artifact, dict) or artifact.get("version") != ARTIFACT_VERSION:
        raise ValueError("This is not a classifier file from this version of SafeRadar AI.")
    return artifact


def save_metrics(result, path):
    payload = {"info": result["info"], "metrics": result["metrics"]}
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return Path(path)


# ---------- using the model ----------

def classify(artifact, description, min_confidence=None):
    """Suggest a category for one description.

    status is 'suggested' (category and confidence given), 'uncertain' (no category: the
    model is not sure, or it knows too few of the words) or never anything else. The text
    itself is not stored or returned.
    """
    threshold = artifact["min_confidence"] if min_confidence is None else min_confidence
    base = {"synthetic": bool(artifact["synthetic"]), "disclaimer": DISCLAIMER}
    pipeline = artifact["pipeline"]

    text = description if isinstance(description, str) else ""
    features = pipeline.named_steps["tfidf"].transform([text])
    if features.nnz < artifact["min_known_words"]:
        return {**base, "status": "uncertain", "category": None, "confidence": None,
                "message": "Too few recognised words to suggest a category."}

    probabilities = pipeline.predict_proba([text])[0]
    best = int(np.argmax(probabilities))
    confidence = round(float(probabilities[best]), 3)
    if confidence < threshold:
        return {**base, "status": "uncertain", "category": None, "confidence": confidence,
                "message": "The model is not confident enough to suggest a category."}
    return {**base, "status": "suggested", "category": str(pipeline.classes_[best]),
            "confidence": confidence, "message": "Category suggested by the model."}


# ---------- charts ----------

def save_charts(result, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = " (synthetic text)" if result["info"]["trained_on_synthetic_data"] else ""
    paths = []

    matrix = np.array(result["metrics"]["grouped_cross_validation"]["logistic_regression"]["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(6.2, 5))
    image = ax.imshow(matrix, cmap="Purples")
    short = [label.replace("Unsafe surroundings", "Unsafe") for label in LABELS]
    ax.set_xticks(range(4), short)
    ax.set_yticks(range(4), short)
    ax.set_xlabel("Predicted category")
    ax.set_ylabel("Actual category")
    for i in range(4):
        for j in range(4):
            ax.text(j, i, int(matrix[i, j]), ha="center", va="center",
                    color="white" if matrix[i, j] > matrix.max() / 2 else NAVY)
    fig.colorbar(image, ax=ax)
    ax.set_title(f"Unseen-template confusion matrix{tag}", fontsize=11, color=NAVY, loc="left", fontweight="bold")
    fig.tight_layout()
    path = out_dir / "nlp_confusion_matrix.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths.append(path)

    cv = result["metrics"]["grouped_cross_validation"]
    inflated = result["metrics"]["random_split_inflated"]
    names = ["Majority\nguess", "Naive Bayes", "Logistic\nRegression"]
    unseen = [cv["majority_baseline"]["macro_f1"], cv["naive_bayes"]["macro_f1"], cv["logistic_regression"]["macro_f1"]]
    seen = [None, inflated["naive_bayes"]["macro_f1"], inflated["logistic_regression"]["macro_f1"]]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    x = np.arange(3)
    ax.bar(x - 0.2, unseen, 0.4, color=PURPLE, label="New templates (honest)")
    ax.bar(x[1:] + 0.2, seen[1:], 0.4, color="#f9a8d4", edgecolor=PURPLE, label="Random split (inflated)")
    ax.set_xticks(x, names)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Macro F1")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_title(f"Honest vs inflated score{tag}", fontsize=11, color=NAVY, loc="left", fontweight="bold")
    fig.tight_layout()
    path = out_dir / "nlp_scores.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    paths.append(path)
    return paths