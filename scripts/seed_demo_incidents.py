"""Put the SYNTHETIC incidents into the app database (as approved demo reports).

Run from the project root, inside the (venv), after scripts.prepare_data:
    python -m scripts.seed_demo_incidents            load them (replaces older demo rows)
    python -m scripts.seed_demo_incidents --remove   delete the demo rows again

Only rows marked synthetic are ever replaced or deleted. Real reports are never touched.
"""
import argparse
import sys

from app import create_app
from app.config import BASE_DIR
from app.extensions import db
from app.ml.eda import load_clean
from app.services.demo_data import load_demo_incidents, remove_demo_incidents

CLEAN_PATH = BASE_DIR / "data" / "processed" / "incidents_clean.csv"


def main():
    parser = argparse.ArgumentParser(description="Load or remove the synthetic demo incidents.")
    parser.add_argument("--remove", action="store_true", help="delete the synthetic rows and stop")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        db.create_all()

        if args.remove:
            print(f"Removed {remove_demo_incidents()} synthetic incidents. Real reports were not touched.")
            return

        if not CLEAN_PATH.exists():
            sys.exit("Clean data not found. Run first:  python -m scripts.prepare_data")

        result = load_demo_incidents(load_clean(CLEAN_PATH))
        print("SYNTHETIC demo data loaded. It is not real.")
        print(f"Replaced {result['removed']} older demo rows, added {result['added']} approved demo incidents.")


if __name__ == "__main__":
    main()