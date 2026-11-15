"""Draw the exploratory charts for the cleaned dataset.

Run from the project root, inside the (venv), after scripts.prepare_data:
    python -m scripts.run_eda

Writes the charts and eda_summary.md into data/eda/.
"""
import json
import sys

from app.config import BASE_DIR
from app.ml.eda import build_summary, load_clean, make_charts, write_summary_markdown

CLEAN_PATH = BASE_DIR / "data" / "processed" / "incidents_clean.csv"
EDA_DIR = BASE_DIR / "data" / "eda"


def run(clean_path=CLEAN_PATH, out_dir=EDA_DIR):
    df = load_clean(clean_path)
    summary = build_summary(df)
    charts = make_charts(df, out_dir)
    write_summary_markdown(summary, charts, out_dir / "eda_summary.md")
    (out_dir / "eda_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary, charts


def main():
    if not CLEAN_PATH.exists():
        sys.exit("Clean data not found. Run first:  python -m scripts.prepare_data")

    summary, charts = run()
    print("SYNTHETIC data. Patterns below come from the generator, not real events.\n")
    print(f"Rows analysed : {summary['rows']}")
    print(f"Period        : {summary['date_from']} to {summary['date_to']}")
    print(f"Busiest hour  : {summary['peak_hour']:02d}:00")
    print(f"Night share   : {summary['night_share_pct']}%")
    print(f"Charts saved  : {len(charts)} files in {EDA_DIR}")


if __name__ == "__main__":
    main()