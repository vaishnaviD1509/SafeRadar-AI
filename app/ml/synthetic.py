"""Generates the SYNTHETIC incident dataset used to develop and test Phases 6 to 8.

Nothing here is real. Every row is invented from rules written in zones.py and below,
and every row carries is_synthetic = True. A model trained on this data only learns
those rules back; its scores must never be described as real-world safety accuracy.
"""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.config import Config
from app.ml.zones import (
    CATEGORIES, CENTER_LAT, CENTER_LON, DEMO_ZONES, STUDY_AREA_RADIUS_DEG,
)

RAW_COLUMNS = [
    "report_id", "description", "category", "severity", "latitude", "longitude",
    "zone", "area_type", "incident_time", "is_synthetic",
]

# Relative chance of an incident in each hour (index 0 = midnight) for a busy-by-day
# place and for a busy-by-night place. Each zone mixes the two using its night_bias.
_DAY_PROFILE = np.array(
    [0.2] * 6
    + [0.8, 1.2, 1.5, 1.2, 1.0, 1.0, 1.1, 1.0, 1.0, 1.2, 1.5, 2.0, 2.5, 2.2, 1.8, 1.2, 0.8, 0.5]
)
_NIGHT_PROFILE = np.array(
    [1.8, 1.4, 1.0, 0.6, 0.4, 0.4] + [0.3] * 12 + [1.0, 1.8, 2.5, 3.0, 2.8, 2.4]
)
_DAY_PROFILE = _DAY_PROFILE / _DAY_PROFILE.sum()
_NIGHT_PROFILE = _NIGHT_PROFILE / _NIGHT_PROFILE.sum()

# Monday to Sunday: a mild rise towards the weekend.
_WEEKDAY_WEIGHTS = np.array([1.0, 1.0, 1.0, 1.05, 1.2, 1.25, 0.9])

_BASE_SEVERITY = {"Harassment": 2.6, "Stalking": 3.0, "Threats": 3.6, "Unsafe surroundings": 2.2}

_TEMPLATES = {
    "Harassment": [
        "A group of men kept making comments at me near the {where} {when} and I felt very uncomfortable.",
        "Someone shouted unwanted remarks and made rude gestures at me while I was walking past the {where} {when}.",
        "A man touched me without permission in the crowd near the {where} {when}.",
        "I was repeatedly teased and whistled at by some boys near the {where} {when}.",
        "A stranger would not stop bothering me and kept asking for my phone number near the {where} {when}.",
    ],
    "Stalking": [
        "A man followed me for several minutes from the {where} {when} and I had to enter a shop to feel safe.",
        "The same person has been waiting near the {where} and following me home {when} for the past few days.",
        "I noticed a bike rider slowly following me near the {where} {when} and he kept looking back at me.",
        "Someone kept taking photos of me without permission near the {where} {when} and then walked behind me.",
        "A stranger followed my auto from the {where} {when} and stopped when I stopped.",
    ],
    "Threats": [
        "A man threatened me with harm after I refused to talk to him near the {where} {when}.",
        "Some people shouted threats at me near the {where} {when} and told me not to come there again.",
        "I received a verbal threat from a drunk man near the {where} {when} and I was afraid for my safety.",
        "A man blocked my way and warned me that something bad would happen to me near the {where} {when}.",
    ],
    "Unsafe surroundings": [
        "The street lights were not working near the {where} {when} and the road was completely dark.",
        "The lane near the {where} was empty and badly lit {when}, and I did not feel safe walking alone.",
        "There were no people around the {where} {when} and a few drunk people were standing in the dark.",
        "The footpath near the {where} was broken and there was no light {when}, which made the area feel unsafe.",
        "The place near the {where} was deserted {when} with no police or guards in sight.",
    ],
}

_ENDINGS = [
    "", "", " Please look into this.", " This was not the first time.", " I want others to be careful.",
]


def local_today():
    """Today's date in local time (India Standard Time by default)."""
    offset = timedelta(minutes=Config.LOCAL_UTC_OFFSET_MINUTES)
    return (datetime.now(timezone.utc) + offset).date()


def _when_phrase(hour):
    if 5 <= hour <= 11:
        return "in the morning"
    if 12 <= hour <= 16:
        return "in the afternoon"
    if 17 <= hour <= 20:
        return "in the evening"
    if hour >= 21:
        return "at night"
    return "late at night"


def generate_synthetic_incidents(n_rows=1500, seed=42, days=330, end_date=None):
    """Return a clean DataFrame of invented incidents (same seed -> same data).

    Incidents fall on the `days` days before `end_date` (never today or later).
    """
    if n_rows < 1 or days < 1:
        raise ValueError("n_rows and days must be at least 1.")

    rng = np.random.default_rng(seed)
    end_date = end_date or local_today()

    zone_p = np.array([z["weight"] for z in DEMO_ZONES])
    zone_p = zone_p / zone_p.sum()
    zone_idx = rng.choice(len(DEMO_ZONES), size=n_rows, p=zone_p)

    dates = [end_date - timedelta(days=k) for k in range(1, days + 1)]
    day_p = np.array([_WEEKDAY_WEIGHTS[d.weekday()] for d in dates])
    day_p = day_p / day_p.sum()
    day_idx = rng.choice(days, size=n_rows, p=day_p)

    limit = STUDY_AREA_RADIUS_DEG - 0.001
    rows = []
    for i in range(n_rows):
        zone = DEMO_ZONES[zone_idx[i]]

        hour_p = (1 - zone["night_bias"]) * _DAY_PROFILE + zone["night_bias"] * _NIGHT_PROFILE
        hour = int(rng.choice(24, p=hour_p / hour_p.sum()))
        minute = int(rng.integers(0, 60))
        when = datetime.combine(dates[day_idx[i]], datetime.min.time()).replace(hour=hour, minute=minute)

        cat_p = np.array(zone["category_weights"])
        category = CATEGORIES[int(rng.choice(len(CATEGORIES), p=cat_p / cat_p.sum()))]

        severity = _BASE_SEVERITY[category] + zone["severity_shift"] + rng.normal(0, 0.9)
        if hour >= 21 or hour < 5:
            severity += 0.3
        severity = int(np.clip(round(severity), 1, 5))

        lat = CENTER_LAT + zone["dlat"] + rng.normal(0, zone["spread"])
        lon = CENTER_LON + zone["dlon"] + rng.normal(0, zone["spread"])
        lat = float(np.clip(lat, CENTER_LAT - limit, CENTER_LAT + limit))
        lon = float(np.clip(lon, CENTER_LON - limit, CENTER_LON + limit))

        templates = _TEMPLATES[category]
        text = templates[int(rng.integers(len(templates)))].format(
            where=zone["where"], when=_when_phrase(hour)
        ) + _ENDINGS[int(rng.integers(len(_ENDINGS)))]

        rows.append({
            "report_id": f"SYN-{i + 1:05d}",
            "description": text,
            "category": category,
            "severity": severity,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "zone": zone["name"],
            "area_type": zone["area_type"],
            "incident_time": when.strftime("%Y-%m-%d %H:%M"),
            "is_synthetic": True,
        })

    df = pd.DataFrame(rows, columns=RAW_COLUMNS)
    return df.sort_values("incident_time").reset_index(drop=True)


def add_realistic_mess(df, seed=7, end_date=None):
    """Return a copy of `df` with deliberate defects, like real collected data has.

    Real report data is never clean. This lets the cleaning step (cleaning.py) be
    practised and tested. Defect counts are small fixed percentages of the rows.
    """
    rng = np.random.default_rng(seed)
    end_date = end_date or local_today()
    out = df.copy().astype(object)
    n = len(out)

    order = list(rng.permutation(n))

    def take(fraction):
        count = max(1, int(round(n * fraction)))
        chosen = order[:count]
        del order[:count]
        return chosen

    for i in take(0.02):                       # missing description
        out.at[i, "description"] = "" if rng.random() < 0.5 else np.nan
    for i in take(0.015):                      # missing coordinate
        out.at[i, "latitude" if rng.random() < 0.5 else "longitude"] = np.nan
    for i in take(0.01):                       # impossible or swapped coordinates
        if rng.random() < 0.5:
            out.at[i, "latitude"], out.at[i, "longitude"] = 0.0, 0.0
        else:
            lat, lon = out.at[i, "latitude"], out.at[i, "longitude"]
            out.at[i, "latitude"], out.at[i, "longitude"] = lon, lat
    for i in take(0.015):                      # severity outside 1 to 5, or missing
        out.at[i, "severity"] = [0, 6, 9, np.nan][int(rng.integers(4))]
    for i in take(0.02):                       # messy capital letters and spaces (fixable)
        value = str(out.at[i, "category"])
        out.at[i, "category"] = [f"  {value.lower()} ", value.upper(), f"{value} "][int(rng.integers(3))]
    for i in take(0.01):                       # a label the system does not know
        out.at[i, "category"] = "Other"
    for i in take(0.01):                       # a time in the future
        future = end_date + timedelta(days=int(rng.integers(2, 10)))
        out.at[i, "incident_time"] = f"{future:%Y-%m-%d} 12:00"

    copies = out.iloc[rng.choice(n, size=max(1, int(round(n * 0.02))), replace=False)].copy()
    copies["report_id"] = copies["report_id"].astype(str) + "-copy"
    out = pd.concat([out, copies], ignore_index=True)

    return out.sample(frac=1, random_state=seed).reset_index(drop=True)