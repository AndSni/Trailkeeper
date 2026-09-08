"""Structure inventory - built assets on the network (culverts, bridges,
signs, ...). Org-wide like trails (BLUEPRINT sec 3); any member views,
editor+ mutates. A structure with a location auto-attaches to the nearest
trail within the same radius tasks use.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser, require_org_role
from app.geo import find_nearest_trail, point_wkt, to_geojson
from app.models import Membership, OrgRole, Structure
from app.schemas import StructureCreateIn, StructureOut, StructureUpdateIn
from app.sync import record_change

router = APIRouter(prefix="/structures", tags=["structures"])

DbSession = Annotated[Session, Depends(get_db)]
EditorMembership = Annotated[Membership, Depends(require_org_role(OrgRole.editor))]


def _select(where_clauses: list):
    geojson = func.ST_AsGeoJSON(Structure.geom).label("geojson")
    return select(Structure, geojson).where(*where_clauses)


def _out(structure: Structure, geojson: str | None) -> StructureOut:
    return StructureOut(
        id=structure.id,
        organisation_id=structure.organisation_id,
        name=structure.name,
        structure_type=structure.structure_type,
        status=structure.status,
        geometry=to_geojson(geojson),
        nearest_trail_id=structure.nearest_trail_id,
        material=structure.material,
        installed_on=structure.installed_on,
        inspection_interval_days=structure.inspection_interval_days,
        notes=structure.notes,
        created_by_id=structure.created_by_id,
        created_at=structure.created_at,
        updated_at=structure.updated_at,
    )


def fetch_structure_out(db: Session, structure_id: uuid.UUID) -> StructureOut | None:
    row = db.execute(
        _select([Structure.id == structure_id, Structure.deleted_at.is_(None)])
    ).first()
    return _out(row[0], row[1]) if row is not None else None


def _get_out(db: Session, structure_id: uuid.UUID) -> StructureOut:
    out = fetch_structure_out(db, structure_id)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Structure not found")
    return out


def _load(db: Session, structure_id: uuid.UUID, org_id: uuid.UUID) -> Structure:
    s = db.get(Structure, structure_id)
    if s is None or s.organisation_id != org_id or s.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Structure not found")
    return s


def _attach_nearest(db: Session, org_id: uuid.UUID, lat: float, lon: float) -> uuid.UUID | None:
    nearest = find_nearest_trail(db, org_id, lat, lon, settings.nearest_trail_max_m)
    return nearest[0] if nearest is not None else None


@router.get("", response_model=list[StructureOut])
def list_structures(
    membership: CurrentMembership,
    db: DbSession,
    trail_id: Annotated[uuid.UUID | None, Query()] = None,
    structure_type: Annotated[str | None, Query(alias="type")] = None,
) -> list[StructureOut]:
    where = [
        Structure.organisation_id == membership.organisation_id,
        Structure.deleted_at.is_(None),
    ]
    if trail_id is not None:
        where.append(Structure.nearest_trail_id == trail_id)
    if structure_type is not None:
        where.append(Structure.structure_type == structure_type)
    rows = db.execute(_select(where).order_by(Structure.name)).all()
    return [_out(s, gj) for s, gj in rows]


@router.post("", response_model=StructureOut, status_code=status.HTTP_201_CREATED)
def create_structure(
    body: StructureCreateIn, membership: EditorMembership, user: CurrentUser, db: DbSession
) -> StructureOut:
    geom = None
    nearest_trail_id = None
    if body.lat is not None and body.lon is not None:
        geom = point_wkt(body.lat, body.lon)
        nearest_trail_id = _attach_nearest(db, membership.organisation_id, body.lat, body.lon)

    structure = Structure(
        organisation_id=membership.organisation_id,
        name=body.name,
        structure_type=body.structure_type.value,
        status=body.status.value,
        geom=geom,
        nearest_trail_id=nearest_trail_id,
        material=body.material,
        installed_on=body.installed_on,
        inspection_interval_days=body.inspection_interval_days,
        notes=body.notes,
        created_by_id=user.id,
    )
    db.add(structure)
    db.flush()
    record_change(
        db, entity_type="structure", entity_id=structure.id, op="upsert",
        organisation_id=structure.organisation_id, actor_id=user.id,
    )
    db.commit()
    return _get_out(db, structure.id)


@router.get("/{structure_id}", response_model=StructureOut)
def get_structure(
    structure_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> StructureOut:
    _load(db, structure_id, membership.organisation_id)
    return _get_out(db, structure_id)


@router.patch("/{structure_id}", response_model=StructureOut)
def update_structure(
    structure_id: uuid.UUID,
    body: StructureUpdateIn,
    membership: EditorMembership,
    user: CurrentUser,
    db: DbSession,
) -> StructureOut:
    structure = _load(db, structure_id, membership.organisation_id)

    if body.name is not None:
        structure.name = body.name
    if body.structure_type is not None:
        structure.structure_type = body.structure_type.value
    if body.status is not None:
        structure.status = body.status.value
    if body.material is not None:
        structure.material = body.material
    if body.installed_on is not None:
        structure.installed_on = body.installed_on
    if body.inspection_interval_days is not None:
        structure.inspection_interval_days = body.inspection_interval_days
    if body.notes is not None:
        structure.notes = body.notes
    if body.lat is not None and body.lon is not None:
        structure.geom = point_wkt(body.lat, body.lon)
        structure.nearest_trail_id = _attach_nearest(
            db, structure.organisation_id, body.lat, body.lon
        )

    record_change(
        db, entity_type="structure", entity_id=structure.id, op="upsert",
        organisation_id=structure.organisation_id, actor_id=user.id,
    )
    db.commit()
    return _get_out(db, structure.id)


@router.delete("/{structure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_structure(
    structure_id: uuid.UUID, membership: EditorMembership, user: CurrentUser, db: DbSession
) -> None:
    structure = _load(db, structure_id, membership.organisation_id)
    structure.deleted_at = datetime.now(UTC)
    record_change(
        db, entity_type="structure", entity_id=structure.id, op="delete",
        organisation_id=structure.organisation_id, actor_id=user.id,
    )
    db.commit()
    return None
