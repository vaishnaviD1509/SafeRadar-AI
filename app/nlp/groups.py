"""Finds which sentence template a description came from.

Why this matters: the synthetic generator builds every report from only a few dozen
sentence templates. If the same template appears in both the training rows and the test
rows, a model can score almost 100% just by recognising a sentence it has already seen.
That would say nothing about new wording.

So the evaluation keeps every template entirely inside either the training part or the
test part (see classifier.py). This module recovers the template by undoing the
substitutions the generator made (place, time of day and closing sentence).

For real reports there are no templates: each distinct text becomes its own group,
which simply keeps exact copies together.
"""
from app.ml.synthetic import _ENDINGS
from app.ml.zones import DEMO_ZONES

_WHERE = sorted({zone["where"] for zone in DEMO_ZONES}, key=len, reverse=True)
_WHEN = ["late at night", "in the morning", "in the afternoon", "in the evening", "at night"]
_ENDS = sorted({e for e in _ENDINGS if e}, key=len, reverse=True)


def template_key(description):
    """The description with its place, time phrase and closing sentence blanked out."""
    text = str(description).strip()
    for ending in _ENDS:
        if text.endswith(ending):
            text = text[: -len(ending)]
            break
    for phrase in _WHERE:
        text = text.replace(phrase, "{where}")
    for phrase in _WHEN:
        text = text.replace(phrase, "{when}")
    return text.strip().lower()