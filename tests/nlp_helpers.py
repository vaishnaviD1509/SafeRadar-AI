"""Shared, cached test model so the classifier is trained only once per test run."""
from functools import lru_cache

from app.nlp.classifier import train_and_evaluate
from tests.risk_helpers import clean_data


@lru_cache(maxsize=1)
def trained_nlp():
    return train_and_evaluate(clean_data())