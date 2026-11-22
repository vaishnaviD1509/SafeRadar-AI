"""Asks an OSRM routing server for routes between two points.

OSRM (Open Source Routing Machine) is a free routing engine. This module sends it the
start and end points and gets back one or more routes as lists of (latitude, longitude)
points, plus the distance and the travel time.

Privacy: the start and end points leave this server for the routing service, so they are
never written to the logs here, and error messages never include them.

The public OSRM demo server is for light use and only offers CAR routes. See config.py for
how to point the app at a server with a walking ("foot") profile.
"""
import math

import requests
from flask import current_app

EARTH_RADIUS_M = 6_371_000.0
MIN_TRIP_M = 50          # a start and end closer than this count as the same place
MAX_TRIP_KM = 30         # keeps requests small and the public server happy
MAX_ROUTES = 3

# How many alternative routes to ask for. A server that does not understand a number is
# asked again with "true" (one alternative).
ALTERNATIVES_TO_TRY = ("3", "true")


class RoutingError(Exception):
    """The routing service could not be used."""


class NoRouteError(RoutingError):
    """The routing service answered, but found no route between the two places."""


def haversine_m(lat1, lon1, lat2, lon2):
    """Straight-line distance in metres between two points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = p2 - p1
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def build_url(start, end):
    """OSRM wants longitude first: /route/v1/<profile>/lon,lat;lon,lat"""
    base = current_app.config["OSRM_BASE_URL"].rstrip("/")
    profile = current_app.config.get("OSRM_PROFILE", "driving")
    (lat1, lon1), (lat2, lon2) = start, end
    return f"{base}/route/v1/{profile}/{lon1:.6f},{lat1:.6f};{lon2:.6f},{lat2:.6f}"


def _parse_route(route):
    unusable = "The routing service gave an answer that could not be used."
    try:
        points = [(float(lat), float(lon)) for lon, lat in route["geometry"]["coordinates"]]
        distance_m = float(route["distance"])
        duration_s = float(route["duration"])
    except (KeyError, TypeError, ValueError):
        raise RoutingError(unusable) from None

    valid = (
        len(points) >= 2
        and math.isfinite(distance_m) and math.isfinite(duration_s)
        and all(math.isfinite(lat) and math.isfinite(lon)
                and -90 <= lat <= 90 and -180 <= lon <= 180 for lat, lon in points)
    )
    if not valid:
        raise RoutingError(unusable)
    return {"points": points, "distance_m": distance_m, "duration_s": duration_s}


def _ask(url, params):
    """One request to the routing server. Returns (data, rejected).

    `rejected` is True when the server did not understand the parameters, so the caller can
    ask again in a simpler way. A network problem raises RoutingError straight away.
    """
    try:
        response = requests.get(
            url, params=params,
            timeout=current_app.config.get("OSRM_TIMEOUT_SECONDS", 8),
            headers={"User-Agent": "SafeRadarAI/1.0 (student project)"},
        )
        try:
            data = response.json()
        except ValueError:
            data = None
        code = data.get("code") if isinstance(data, dict) else None
        if code in ("NoRoute", "NoSegment"):
            raise NoRouteError("No route was found between these two places.")
        if code in ("InvalidQuery", "InvalidValue", "InvalidOptions"):
            return data, True
        response.raise_for_status()
    except NoRouteError:
        raise
    except requests.RequestException:
        # Deliberately no details: the message of a network error contains the coordinates.
        raise RoutingError("The routing service could not be reached.") from None
    return data, False


def fetch_routes(start, end):
    """Up to three routes from start to end, each {points, distance_m, duration_s}.

    Raises NoRouteError when there is no route and RoutingError for any other problem.
    """
    url = build_url(start, end)
    data, rejected = None, True
    for alternatives in ALTERNATIVES_TO_TRY:
        params = {"alternatives": alternatives, "overview": "full",
                  "geometries": "geojson", "steps": "false"}
        data, rejected = _ask(url, params)
        if not rejected:
            break
    if rejected:
        raise RoutingError("The routing service gave an answer that could not be used.")

    if not isinstance(data, dict) or data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError("The routing service gave an answer that could not be used.")
    return [_parse_route(route) for route in data["routes"][:MAX_ROUTES]]


def thin(points, max_points):
    """Keep at most `max_points` points, spread evenly, always keeping the first and last."""
    points = list(points)
    if max_points < 2 or len(points) <= max_points:
        return points
    last = len(points) - 1
    indexes = sorted({round(i * last / (max_points - 1)) for i in range(max_points)})
    return [points[i] for i in indexes]


def sample_along(points, spacing_m=100.0, max_samples=500):
    """Points along a route line, one every `spacing_m` metres, plus the start and the end.

    If the route is so long that this would give more than `max_samples`, the spacing grows.
    """
    if not points:
        return []
    if len(points) == 1:
        return [points[0]]

    gaps = [haversine_m(*points[i], *points[i + 1]) for i in range(len(points) - 1)]
    total = sum(gaps)
    if total == 0:
        return [points[0]]

    spacing = max(spacing_m, total / (max_samples - 1))
    samples = [points[0]]
    target, walked, i = spacing, 0.0, 0
    while target < total:
        while i < len(gaps) and walked + gaps[i] < target:
            walked += gaps[i]
            i += 1
        if i >= len(gaps):
            break
        t = (target - walked) / gaps[i] if gaps[i] else 0.0
        samples.append((
            points[i][0] + t * (points[i + 1][0] - points[i][0]),
            points[i][1] + t * (points[i + 1][1] - points[i][1]),
        ))
        target += spacing
    samples.append(points[-1])
    return samples