"""Train and test the risk model, then save it.

Run from the project root, inside the (venv), after scripts.prepare_data:
    python -m scripts.train_risk_model

Writes into ml_models/:
    risk_model.joblib              the model the web app loads
    risk_metrics.json              every measured number
    risk_confusion_matrix.png      chart
    risk_feature_importance.png    chart
"""
import sys

from app.config import BASE_DIR
from app.ml.eda import load_clean
from app.ml.risk_model import save_artifact, save_charts, save_metrics, train_and_evaluate

CLEAN_PATH = BASE_DIR / "data" / "processed" / "incidents_clean.csv"
MODEL_DIR = BASE_DIR / "ml_models"


def run(clean_path=CLEAN_PATH, model_dir=MODEL_DIR):
    result = train_and_evaluate(load_clean(clean_path))
    save_artifact(result["artifact"], model_dir / "risk_model.joblib")
    save_metrics(result, model_dir / "risk_metrics.json")
    save_charts(result, model_dir)
    return result


def _row(name, m):
    return f"{name:<22}{m['accuracy']:<10}{m['macro_f1']:<10}{m['within_one_level']:<10}"


def main():
    if not CLEAN_PATH.exists():
        sys.exit("Clean data not found. Run first:  python -m scripts.prepare_data")

    result = run()
    info, metrics = result["info"], result["metrics"]

    print(info["data_note"])
    print(f"\nTraining period : {info['period_from']} to {info['cutoff_date']} (exclusive)")
    print(f"Test period     : {info['cutoff_date']} to {info['period_to']}  (never seen in training)")
    print(f"Modelled cells  : {info['modelled_cells']} (all other places are UNKNOWN)")
    print(f"Train / test rows: {info['train_rows']} / {info['test_rows']}\n")

    print(f"{'Model':<22}{'Accuracy':<10}{'Macro F1':<10}{'Within 1':<10}")
    for key, name in (("majority_baseline", "Majority guess"),
                      ("persistence_baseline", "Persistence guess"),
                      ("decision_tree", "Decision Tree"),
                      ("random_forest", "Random Forest (used)")):
        print(_row(name, metrics[key]))

    print("\nRandom Forest by level (test period):")
    for level, m in metrics["random_forest"]["per_level"].items():
        print(f"  {level:<9} precision {m['precision']:<7} recall {m['recall']:<7} "
              f"f1 {m['f1']:<7} (n={m['support']})")
    print("\nMost important features:", ", ".join(list(info["feature_importance"])[:3]))
    print(f"\nSaved to {MODEL_DIR}")


if __name__ == "__main__":
    main()