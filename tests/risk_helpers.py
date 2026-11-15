"""Shared, cached test data so the model is trained only once per test run."""
from datetime import date
from functools import lru_cache

import pandas as pd

from app.ml.cleaning import clean_incidents
from app.ml.risk_model import train_and_evaluate
from app.ml.synthetic import add_realistic_mess, generate_synthetic_incidents

END = date(2026, 11, 1)
REFERENCE = pd.Timestamp("2026-11-01 23:59")


@lru_cache(maxsize=1)
def clean_data():
    generated = generate_synthetic_incidents(n_rows=2500, seed=11, days=330, end_date=END)
    raw = add_realistic_mess(generated, seed=12, end_date=END)
    clean, _ = clean_incidents(raw, reference_time=REFERENCE)
    return clean


@lru_cache(maxsize=1)
def trained():
    return train_and_evaluate(clean_data())