"""Trail CRUD and GPX import.

Trails are org-wide (the whole network on one map, per Trail Sentinel) - not
scoped to a project. Any member can view them; mutating needs admin+ for
now (see docs/BLUEPRINT.md sec 13 - a project-lead carve-out for trail
editing can follow once there's a concrete need for it).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

import gpxpy
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from geoalchemy2 import Geography
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import CurrentMembership, CurrentUser, require_org_role
from app.geo import linestring_wkt, to_geojson
from app.models import Membership, OrgRole, Trail
from app.schemas import TrailCreateIn, TrailOut, TrailUpdateIn

router = APIRouter(prefix="/trails", tags=["trails"])

DbSession = Annotated[Session, Depends(get_db)]
AdminMembership = Annotated[Membership, Depends(require_org_role(OrgRole.admin))]


def _out(trail: Trail, geojson: str, length_m: float) -> TrailOut:
    return TrailOut(
        id=trail.id,
        organisation_id=trail.organisation_id,
        name=trail.name,
        activity=trail.activity,
        difficulty=trail.difficulty,
        status=trail.status,
        source=trail.source,
        length_m=round(length_m, 1),
        geometry=to_geojson(geojson),
        created_at=trail.created_at,
        updated_at=trail.updated_at,
    )


def _select_trails(where_clauses: list):
    """Trail rows alongside their GeoJSON + metre length, computed in
    Postgres in the same round trip - geometry never leaves as anything but
    GeoJSON, and length is never stored (it's derived from the line)."""
    geojson = func.ST_AsGeoJSON(Trail.geom).label("geojson")
    length_m = func.ST_Length(func.cast(Trail.geom, Geography)).label("length_m")
    return select(Trail, geojson, length_m).where(*where_clauses)


@router.get("", response_model=list[TrailOut])
def list_trails(membership: CurrentMembership, db: DbSession) -> list[TrailOut]:
    stmt = _select_trails(
        [Trail.organisation_id == membership.organisation_id, Trail.deleted_at.is_(None)]
    ).order_by(Trail.name)
    return [_out(t, gj, ln) for t, gj, ln in db.execute(stmt).all()]


@router.post("", response_model=TrailOut, status_code=status.HTTP_201_CREATED)
def create_trail(
    body: TrailCreateIn, membership: AdminMembership, user: CurrentUser, db: DbSession
) -> TrailOut:
    trail = Trail(
        organisation_id=membership.organisation_id,
        name=body.name,
        activity=body.activity,
        difficulty=body.difficulty,
        status=body.status.value,
        geom=linestring_wkt(body.points),
        source="drawn",
        created_by_id=user.id,
    )
    db.add(trail)
    db.commit()
    return _get_out(db, trail.id)


@router.post("/import-gpx", response_model=list[TrailOut], status_code=status.HTTP_201_CREATED)
async def import_gpx(
    membership: AdminMembership,
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    activity: Annotated[str, Form()] = "mtb",
) -> list[TrailOut]:
    """One GPX file may hold several tracks/segments; each becomes its own
    Trail, named after the GPX track name (falling back to the file name)."""
    raw = await file.read()
    try:
        gpx = gpxpy.parse(raw.decode("utf-8", errors="replace"))
    except Exception as exc:  # gpxpy raises its own GPXXMLSyntaxException
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Not a valid GPX file: {exc}") from exc

    base_name = (file.filename or "Imported trail").rsplit(".", 1)[0]
    created: list[Trail] = []
    for t_index, track in enumerate(gpx.tracks):
        for s_index, segment in enumerate(track.segments):
            points = [(p.latitude, p.longitude) for p in segment.points]
            if len(points) < 2:
                continue
            name = track.name or (
                base_name if t_index == 0 and s_index == 0 else f"{base_name} ({t_index}.{s_index})"
            )
            trail = Trail(
                organisation_id=membership.organisation_id,
                name=name,
                activity=activity,
                geom=linestring_wkt(points),
                source="imported",
                created_by_id=user.id,
            )
            db.add(trail)
            created.append(trail)

    if not created:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "GPX file has no track with 2+ points")
    db.commit()
    return [_get_out(db, t.id) for t in created]


@router.get("/{trail_id}", response_model=TrailOut)
def get_trail(trail_id: uuid.UUID, membership: CurrentMembership, db: DbSession) -> TrailOut:
    return _get_out(db, trail_id, org_id=membership.organisation_id)


@router.patch("/{trail_id}", response_model=TrailOut)
def update_trail(
    trail_id: uuid.UUID, body: TrailUpdateIn, membership: AdminMembership, db: DbSession
) -> TrailOut:
    trail = _load(db, trail_id, membership.organisation_id)
    if body.name is not None:
        trail.name = body.name
    if body.difficulty is not None:
        trail.difficulty = body.difficulty
    if body.status is not None:
        trail.status = body.status.value
    db.commit()
    return _get_out(db, trail.id)


@router.delete("/{trail_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trail(trail_id: uuid.UUID, membership: AdminMembership, db: DbSession) -> None:
    trail = _load(db, trail_id, membership.organisation_id)
    trail.deleted_at = datetime.now(UTC)
    db.commit()
    return None


def _load(db: Session, trail_id: uuid.UUID, org_id: uuid.UUID) -> Trail:
    trail = db.get(Trail, trail_id)
    if trail is None or trail.organisation_id != org_id or trail.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trail not found")
    return trail


def _get_out(db: Session, trail_id: uuid.UUID, org_id: uuid.UUID | None = None) -> TrailOut:
    where = [Trail.id == trail_id, Trail.deleted_at.is_(None)]
    if org_id is not None:
        where.append(Trail.organisation_id == org_id)
    row = db.execute(_select_trails(where)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trail not found")
    trail, geojson, length_m = row
    return _out(trail, geojson, length_m)
