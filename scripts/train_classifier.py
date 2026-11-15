"""Train and test the incident text classifier, then save it.

Run from the project root, inside the (venv), after scripts.prepare_data:
    python -m scripts.train_classifier

Writes into ml_models/:
    incident_classifier.joblib     the model the web app loads
    nlp_metrics.json               every measured number
    nlp_confusion_matrix.png       chart
    nlp_scores.png                 chart
"""
import sys

from app.config import BASE_DIR
from app.ml.eda import load_clean
from app.nlp.classifier import save_artifact, save_charts, save_metrics, train_and_evaluate

CLEAN_PATH = BASE_DIR / "data" / "processed" / "incidents_clean.csv"
MODEL_DIR = BASE_DIR / "ml_models"


def run(clean_path=CLEAN_PATH, model_dir=MODEL_DIR):
    result = train_and_evaluate(load_clean(clean_path))
    save_artifact(result["artifact"], model_dir / "incident_classifier.joblib")
    save_metrics(result, model_dir / "nlp_metrics.json")
    save_charts(result, model_dir)
    return result


def main():
    if not CLEAN_PATH.exists():
        sys.exit("Clean data not found. Run first:  python -m scripts.prepare_data")

    result = run()
    info, metrics = result["info"], result["metrics"]
    cv, inflated, check = (metrics["grouped_cross_validation"], metrics["random_split_inflated"],
                           metrics["hand_written_check"])

    print(info["data_note"])
    print(f"\nRows: {info['rows']}   Distinct sentence templates: {info['distinct_templates']}")
    print(f"Vocabulary size: {info['vocabulary_size']} words/word pairs\n")

    print("A) New wording (templates the model never saw while training)")
    print(f"   {'Model':<22}{'Accuracy':<10}{'Macro F1':<10}")
    for key, name in (("majority_baseline", "Majority guess"), ("naive_bayes", "Naive Bayes"),
                      ("logistic_regression", "Logistic Regression (used)")):
        print(f"   {name:<28}{cv[key]['accuracy']:<10}{cv[key]['macro_f1']:<10}")
    print(f"   Logistic Regression macro F1 per fold: {cv['logistic_regression']['fold_macro_f1']}")

    print("\nB) Ordinary random split (INFLATED: same templates on both sides)")
    print(f"   Logistic Regression accuracy {inflated['logistic_regression']['accuracy']}, "
          f"macro F1 {inflated['logistic_regression']['macro_f1']}")

    print(f"\nC) {check['sentences']} hand-written sentences, never used in training")
    print(f"   accuracy {check['accuracy']}, macro F1 {check['macro_f1']}, "
          f"suggested at confidence >= {info['min_confidence']}: {check['suggested_at_threshold']}")

    print("\nConfidence cut-off (new-wording test):")
    for row in metrics["confidence_table"]:
        print(f"   >= {row['min_confidence']:<4} suggested {row['share_suggested']:<7} "
              f"correct when suggested {row['accuracy_when_suggested']}")

    print("\nWords that point to each category (stemmed):")
    for label, words in info["top_terms"].items():
        print(f"   {label:<20}{', '.join(words[:6])}")
    print(f"\nSaved to {MODEL_DIR}")


if __name__ == "__main__":
    main()