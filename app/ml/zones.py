"""Demo zones used to build the SYNTHETIC dataset.

IMPORTANT: these zones are generic and invented for development. They are placed
as small offsets around the map centre and are NOT real neighbourhoods. The
patterns attached to them (busy hours, incident mix, severity) are assumptions
written by the developer so the machine-learning pipeline has something to learn.
They say nothing about how safe any real place in Kalaburagi is.
"""
from app.config import Config
from app.models.incident import CATEGORIES

CENTER_LAT, CENTER_LON = Config.DEFAULT_MAP_CENTER

# Rows farther than this (in degrees, about 28 km) from the centre are rejected as
# bad coordinates during cleaning.
STUDY_AREA_RADIUS_DEG = 0.25

# Order of category_weights follows CATEGORIES:
# Harassment, Stalking, Threats, Unsafe surroundings
DEMO_ZONES = [
    dict(name="Demo Zone 1 - Market area", area_type="market", where="market",
         dlat=0.004, dlon=-0.003, spread=0.003, weight=0.20, night_bias=0.15,
         category_weights=(0.50, 0.15, 0.10, 0.25), severity_shift=0.0),
    dict(name="Demo Zone 2 - Bus stand area", area_type="bus stand", where="bus stand",
         dlat=-0.006, dlon=0.002, spread=0.003, weight=0.18, night_bias=0.30,
         category_weights=(0.40, 0.25, 0.15, 0.20), severity_shift=0.2),
    dict(name="Demo Zone 3 - Railway area", area_type="railway station", where="railway station",
         dlat=-0.012, dlon=-0.008, spread=0.0035, weight=0.14, night_bias=0.45,
         category_weights=(0.30, 0.20, 0.25, 0.25), severity_shift=0.4),
    dict(name="Demo Zone 4 - College area", area_type="college", where="college gate",
         dlat=0.015, dlon=0.010, spread=0.004, weight=0.12, night_bias=0.10,
         category_weights=(0.35, 0.45, 0.10, 0.10), severity_shift=-0.1),
    dict(name="Demo Zone 5 - Residential area", area_type="residential", where="residential lane",
         dlat=0.010, dlon=-0.015, spread=0.005, weight=0.10, night_bias=0.25,
         category_weights=(0.20, 0.30, 0.20, 0.30), severity_shift=-0.2),
    dict(name="Demo Zone 6 - Park and lake side", area_type="park", where="park and lake side",
         dlat=0.002, dlon=0.018, spread=0.004, weight=0.08, night_bias=0.55,
         category_weights=(0.20, 0.15, 0.15, 0.50), severity_shift=0.1),
    dict(name="Demo Zone 7 - Ring road outskirts", area_type="outskirts", where="ring road",
         dlat=-0.020, dlon=0.014, spread=0.006, weight=0.10, night_bias=0.75,
         category_weights=(0.10, 0.15, 0.30, 0.45), severity_shift=0.5),
    dict(name="Demo Zone 8 - Commercial street", area_type="commercial", where="main commercial street",
         dlat=0.007, dlon=0.006, spread=0.003, weight=0.08, night_bias=0.20,
         category_weights=(0.45, 0.20, 0.10, 0.25), severity_shift=0.0),
]

ZONE_NAMES = [z["name"] for z in DEMO_ZONES]