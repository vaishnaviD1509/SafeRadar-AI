"""Turns a report description into clean, comparable words.

Steps: lowercase -> keep letters only -> drop common filler words -> reduce each word
to its stem ("following", "followed" and "follows" all become "follow").

Only English is handled. Words the model has never seen are ignored, and text with too
few known words is marked "uncertain" instead of being guessed (see classifier.py).

No internet download is needed: the stemmer is an algorithm and the filler-word list
ships with scikit-learn.
"""
import re
from functools import lru_cache

from nltk.stem import PorterStemmer
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

# Small words like "the" or "and" carry no meaning, but negations change it:
# "no light" is not "light", so these are kept.
NEGATIONS = {"no", "not", "nor", "never", "cannot", "without", "nobody", "nothing", "none", "against"}
STOP_WORDS = frozenset(ENGLISH_STOP_WORDS) - NEGATIONS

_WORD = re.compile(r"[a-z]+")
_stemmer = PorterStemmer()


@lru_cache(maxsize=None)
def _stem(word):
    return _stemmer.stem(word)


def normalize_text(text):
    """'A man was FOLLOWING me!' -> 'man follow'. Anything that is not text gives ''."""
    if not isinstance(text, str):
        return ""
    words = _WORD.findall(text.lower())
    return " ".join(_stem(w) for w in words if len(w) > 1 and w not in STOP_WORDS)