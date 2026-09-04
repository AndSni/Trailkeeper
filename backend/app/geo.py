"""Small PostGIS helpers shared by the trails/tasks routes.

Geometry travels over the API as GeoJSON (what MapLibre and every other
mapping tool expects) and is stored in Postgres as native `geometry` columns
via GeoAlchemy2. These helpers are the only place that translates between
the two, plus the nearest-trail lookup used to auto-attach a new task.
"""

from __future__ import annotations

import json

from geoalchemy2 import Geography, WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Trail


def point_wkt(lat: float, lon: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def linestring_wkt(points: list[tuple[float, float]]) -> WKTElement:
    """`points` is a list of (lat, lon) pairs, in order along the line."""
    if len(points) < 2:
        raise ValueError("a line needs at least 2 points")
    coords = ", ".join(f"{lon} {lat}" for lat, lon in points)
    return WKTElement(f"LINESTRING({coords})", srid=4326)


def to_geojson(raw: str | None) -> dict | None:
    """Parses an `ST_AsGeoJSON(...)` result column into a GeoJSON dict."""
    return json.loads(raw) if raw is not None else None


def find_nearest_trail(
    db: Session, organisation_id, lat: float, lon: float, max_m: float
) -> tuple[object, float] | None:
    """Returns (trail_id, distance_m) for the closest trail within max_m, or
    None if nothing in the org is that close. Distance is measured on the
    geography cast, i.e. real metres rather than degrees."""
    point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    dist = func.ST_Distance(
        func.cast(Trail.geom, Geography), func.cast(point, Geography)
    ).label("dist_m")
    row = db.execute(
        select(Trail.id, dist)
        .where(Trail.organisation_id == organisation_id, Trail.deleted_at.is_(None))
        .order_by(dist)
        .limit(1)
    ).first()
    if row is None or row.dist_m > max_m:
        return None
    return row.id, float(row.dist_m)


def trail_length_m(db: Session, geom: WKTElement) -> float:
    """Length in metres of a not-yet-persisted LineString (geography cast)."""
    return float(db.scalar(select(func.ST_Length(func.cast(geom, Geography)))))
