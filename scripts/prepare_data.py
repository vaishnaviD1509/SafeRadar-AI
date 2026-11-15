"""Create the synthetic dataset and clean it.

Run from the project root, inside the (venv):
    python -m scripts.prepare_data
    python -m scripts.prepare_data --rows 2000 --seed 7

Writes:
    data/raw/synthetic_incidents_raw.csv          (deliberately messy, SYNTHETIC)
    data/processed/incidents_clean.csv            (cleaned, SYNTHETIC)
    data/processed/data_quality_report.json       (what was fixed or removed)
"""
import argparse
import json
from pathlib import Path

from app.config import BASE_DIR
from app.ml.cleaning import clean_incidents
from app.ml.synthetic import add_realistic_mess, generate_synthetic_incidents, local_today

RAW_PATH = BASE_DIR / "data" / "raw" / "synthetic_incidents_raw.csv"
CLEAN_PATH = BASE_DIR / "data" / "processed" / "incidents_clean.csv"
REPORT_PATH = BASE_DIR / "data" / "processed" / "data_quality_report.json"


def run(rows=1500, seed=42, days=330, raw_path=RAW_PATH, clean_path=CLEAN_PATH, report_path=REPORT_PATH):
    raw_path, clean_path, report_path = Path(raw_path), Path(clean_path), Path(report_path)
    for path in (raw_path, clean_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    today = local_today()
    generated = generate_synthetic_incidents(n_rows=rows, seed=seed, days=days, end_date=today)
    raw = add_realistic_mess(generated, seed=seed + 1, end_date=today)
    raw.to_csv(raw_path, index=False)

    clean, report = clean_incidents(raw)
    clean_out = clean.copy()
    clean_out["incident_time"] = clean_out["incident_time"].dt.strftime("%Y-%m-%d %H:%M")
    clean_out.to_csv(clean_path, index=False)

    report["generated_rows_before_defects"] = int(len(generated))
    report["note"] = "All data is SYNTHETIC. It was generated for development and is not real."
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Create and clean the synthetic incident dataset.")
    parser.add_argument("--rows", type=int, default=1500, help="how many incidents to generate")
    parser.add_argument("--seed", type=int, default=42, help="random seed (same seed = same data)")
    parser.add_argument("--days", type=int, default=330, help="how many past days to spread them over")
    args = parser.parse_args()

    report = run(rows=args.rows, seed=args.seed, days=args.days)

    print("SYNTHETIC data created. It is not real.\n")
    print(f"Raw rows (with defects) : {report['rows_in']}")
    print(f"Clean rows kept         : {report['rows_out']}")
    print(f"Rows removed            : {report['rows_dropped']}")
    for reason, count in report["dropped_by_reason"].items():
        print(f"  - {reason}: {count}")
    print(f"Category text fixed     : {report['fixed']['category_text_fixed']}")
    print(f"\nRaw file  : {RAW_PATH}")
    print(f"Clean file: {CLEAN_PATH}")
    print(f"Report    : {REPORT_PATH}")


if __name__ == "__main__":
    main()