"""Plans routes between two places and scores each one with the risk model.

How a route is scored
---------------------
1. The routing service returns up to three routes as lines of points.
2. Each line is sampled every 100 m.
3. Each sample falls in a grid square. If the model has an estimate for that square (for
   the time slot and day type of the departure time), the sample gets an "expected level":
   1 for Low, 2 for Moderate, 3 for High, weighted by the model's probabilities.
4. The route's RISK INDEX is the average expected level over the samples that have an
   estimate, stretched to 0 to 100 (0 = every known part is Low, 100 = every known part
   is High).

Which route is suggested
------------------------
When at least two routes have a risk index, the one with the lowest index is suggested.
The suggestion says how confident the difference is: "clear" when the gap to the next route
is at least 5 points, "slight" when it is smaller. Identical scores give no suggestion.

Honesty rules
-------------
* The index is RELATIVE, like every level in this project: it compares places and times
  inside the training data. A low index never means "safe", and the app never says "safe".
* A sample with no estimate is UNKNOWN. It is never counted as Low. Every route reports how
  much of it was covered.
* A route with less than half of its length covered gets no index at all, and a route
  without an index is left out of the ranking (the message says so).
"""
from flask import current_app

from app.ml.risk_dataset import SLOT_HOURS, SLOT_NAMES, cell_id, cell_of, slot_of_hour
from app.ml.risk_model import DISCLAIMER
from app.services.heatmap import build_risk_grid
from app.services.routing import fetch_routes, sample_along, thin
from app.utils.timeutils import local_now

LEVEL_VALUE = {"Low": 1.0, "Moderate": 2.0, "High": 3.0}
SAMPLE_SPACING_M = 100.0
MAX_SAMPLES = 500
MAX_DRAW_POINTS = 600
MIN_COVERAGE = 0.5        # share of a route that must have estimates before it gets an index
MIN_DIFFERENCE = 5.0      # index points for a "clear" difference between two routes


def grid_lookup(grid):
    """{cell id: {"Low": p, "Moderate": p, "High": p}} from build_risk_grid()."""
    return {cell["id"]: cell["probabilities"] for cell in grid["cells"]}


def score_route(samples, lookup):
    """Risk numbers for a list of (lat, lon) samples. Unknown samples are never counted as Low."""
    total = len(samples)
    expected = []
    counts = {"Low": 0, "Moderate": 0, "High": 0}
    for lat, lon in samples:
        cell = cell_of(lat, lon)
        probabilities = lookup.get(cell_id(*cell)) if cell else None
        if not probabilities:
            continue
        expected.append(sum(LEVEL_VALUE[level] * probabilities.get(level, 0.0) for level in LEVEL_VALUE))
        counts[max(LEVEL_VALUE, key=lambda level: probabilities.get(level, 0.0))] += 1

    known = len(expected)
    coverage = known / total if total else 0.0
    comparable = known > 0 and coverage >= MIN_COVERAGE
    risk_index = round((sum(expected) / known - 1) / 2 * 100, 1) if comparable else None

    def share(n):
        return round(100.0 * n / total, 1) if total else 0.0

    coverage_pct = round(coverage * 100)
    return {
        "samples": total,
        "known_samples": known,
        "coverage_pct": coverage_pct,
        "unknown_pct": 100 - coverage_pct,
        "high_pct": share(counts["High"]),
        "moderate_pct": share(counts["Moderate"]),
        "low_pct": share(counts["Low"]),
        "risk_index": risk_index,
    }


def recommend(routes, risk_model=True):
    """Which route is fastest, and which one to suggest by estimated risk.

    Returns {"fastest_id", "lowest_risk_id", "confidence", "message"}. confidence is "clear",
    "slight" or None. lowest_risk_id is None when the data cannot separate the routes.
    """
    fastest = min(routes, key=lambda route: route["duration_min"])
    result = {"fastest_id": fastest["id"], "lowest_risk_id": None, "confidence": None}

    if len(routes) == 1:
        result["message"] = ("Only one route was found, so there is nothing to compare. "
                             "Try a start and an end that are further apart.")
        return result
    if not risk_model:
        result["message"] = "The risk model has not been trained yet, so the routes cannot be compared by risk."
        return result

    scored = sorted(
        (r for r in routes if r["risk"] and r["risk"]["risk_index"] is not None),
        key=lambda r: r["risk"]["risk_index"],
    )
    if len(scored) < 2:
        result["message"] = ("There is too little data to compare the routes by risk. "
                             f"Unknown does not mean safe. Route {fastest['id']} is the fastest.")
        return result

    best, second = scored[0], scored[1]
    gap = round(second["risk"]["risk_index"] - best["risk"]["risk_index"], 1)
    if gap <= 0:
        result["message"] = ("The routes have the same estimated risk. "
                             "Choose by travel time and your own judgement.")
        return result

    result["lowest_risk_id"] = best["id"]
    result["confidence"] = "clear" if gap >= MIN_DIFFERENCE else "slight"

    if result["confidence"] == "clear":
        head = f"Suggested: Route {best['id']} has the lowest estimated relative risk."
    else:
        head = (f"Suggested: Route {best['id']} has slightly lower estimated risk, but the difference is "
                f"small (under {MIN_DIFFERENCE:g} points), so the routes are close.")

    extra = round(best["duration_min"] - fastest["duration_min"], 1)
    if best["id"] == fastest["id"] or extra <= 0:
        timing = "It is also the fastest route."
    else:
        timing = f"It takes about {extra:g} min longer than the fastest route (Route {fastest['id']})."

    parts = [head, timing]
    if len(scored) < len(routes):
        parts.append("Routes with too little data were left out of this ranking.")
    parts.append("Lower does not mean safe.")
    result["message"] = " ".join(parts)
    return result


def plan_routes(start, end, when_local=None):
    """Routes from start to end, each scored for the time of departure.

    start and end are (lat, lon). Raises RoutingError (or NoRouteError) when the routing
    service cannot help. Works without a risk model: the routes then carry no risk numbers.
    """
    when_local = when_local or local_now()
    routes = fetch_routes(start, end)

    slot = slot_of_hour(when_local.hour)
    weekend = int(when_local.weekday() >= 5)
    grid = build_risk_grid(slot, weekend)
    lookup = grid_lookup(grid) if grid is not None else None

    planned = []
    for number, route in enumerate(routes, start=1):
        samples = sample_along(route["points"], SAMPLE_SPACING_M, MAX_SAMPLES)
        planned.append({
            "id": number,
            "distance_km": round(route["distance_m"] / 1000, 2),
            "duration_min": round(route["duration_s"] / 60, 1),
            "geometry": [[round(lat, 5), round(lon, 5)] for lat, lon in thin(route["points"], MAX_DRAW_POINTS)],
            "risk": score_route(samples, lookup) if lookup is not None else None,
            "labels": [],
        })

    recommendation = recommend(planned, risk_model=lookup is not None)
    for route in planned:
        if route["id"] == recommendation["fastest_id"]:
            route["labels"].append("Fastest")
        if route["id"] == recommendation["lowest_risk_id"]:
            route["labels"].append(
                "Lowest estimated risk" if recommendation["confidence"] == "clear" else "Slightly lower risk")

    return {
        "status": "ok",
        "travel_mode": current_app.config.get("OSRM_PROFILE", "driving"),
        "slot": SLOT_NAMES[slot],
        "slot_index": slot,
        "slot_hours": SLOT_HOURS[slot],
        "is_weekend": bool(weekend),
        "risk_model": lookup is not None,
        "synthetic": bool(grid["synthetic"]) if grid is not None else None,
        "disclaimer": DISCLAIMER,
        "routes": planned,
        "recommendation": recommendation,
    }