"""SegmentWorkRecord CRUD + productivity rollups - the segment-timing model
(docs/BLUEPRINT.md sec 10). Rates, throughput and person-hours are derived
here, never stored.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2 import Geography
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz import is_org_admin, require_project_member
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser
from app.models import JobType, SegmentWorkRecord, Trail, User
from app.schemas import (
    SegmentRollupGroup,
    SegmentRollupOut,
    SegmentWorkCreateIn,
    SegmentWorkOut,
    SegmentWorkUpdateIn,
)
from app.sync import record_change

router = APIRouter(prefix="/segment-work", tags=["segment-work"])

DbSession = Annotated[Session, Depends(get_db)]

_ROLLUP_DIMS = ("job_type", "trail", "member", "week")


# --------------------------------------------------------------------------- #
# Derived numbers
# --------------------------------------------------------------------------- #


def _derive(active_seconds: int, quantity: float, crew_size: int, expected_rate: float | None):
    person_hours = round(active_seconds / 3600 * crew_size, 3)
    rate = round((active_seconds / 60) / quantity, 2) if quantity and quantity > 0 else None
    throughput = round(quantity / (active_seconds / 3600), 3) if active_seconds > 0 else None
    vs_expected = (
        round(rate - float(expected_rate), 2)
        if rate is not None and expected_rate is not None
        else None
    )
    return person_hours, rate, throughput, vs_expected


def _geojson(db: Session, record_id: uuid.UUID) -> dict | None:
    raw = db.scalar(
        select(func.ST_AsGeoJSON(SegmentWorkRecord.geom)).where(SegmentWorkRecord.id == record_id)
    )
    return json.loads(raw) if raw else None


def _out(db: Session, rec: SegmentWorkRecord) -> SegmentWorkOut:
    expected = None
    if rec.job_type_id is not None:
        jt = db.get(JobType, rec.job_type_id)
        expected = jt.expected_rate if jt is not None else None
    quantity = float(rec.quantity)
    person_hours, rate, throughput, vs_expected = _derive(
        rec.active_seconds, quantity, rec.crew_size, expected
    )
    return SegmentWorkOut(
        id=rec.id,
        organisation_id=rec.organisation_id,
        project_id=rec.project_id,
        job_type_id=rec.job_type_id,
        trail_id=rec.trail_id,
        geometry=_geojson(db, rec.id),
        quantity=quantity,
        unit=rec.unit,
        quantity_source=rec.quantity_source,
        started_at=rec.started_at,
        ended_at=rec.ended_at,
        active_seconds=rec.active_seconds,
        pauses=rec.pauses,
        crew_size=rec.crew_size,
        equipment=rec.equipment,
        notes=rec.notes,
        created_by_id=rec.created_by_id,
        person_hours=person_hours,
        rate_min_per_unit=rate,
        throughput_per_hour=throughput,
        vs_expected_min_per_unit=vs_expected,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def fetch_segment_out(db: Session, record_id: uuid.UUID) -> SegmentWorkOut | None:
    rec = db.get(SegmentWorkRecord, record_id)
    if rec is None or rec.deleted_at is not None:
        return None
    return _out(db, rec)


# --------------------------------------------------------------------------- #
# Geometry + measured quantity
# --------------------------------------------------------------------------- #


def _geom_expr(geometry: dict | None):
    if geometry is None:
        return None
    return func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)


def _measured_quantity(db: Session, record_id: uuid.UUID, unit: str) -> float | None:
    geog = func.cast(SegmentWorkRecord.geom, Geography)
    if unit == "km":
        val = db.scalar(
            select(func.ST_Length(geog)).where(SegmentWorkRecord.id == record_id)
        )
        return round(val / 1000, 3) if val is not None else None
    if unit == "m2":
        val = db.scalar(
            select(func.ST_Area(geog)).where(SegmentWorkRecord.id == record_id)
        )
        return round(val, 3) if val is not None else None
    return None  # count / hours can't be measured from geometry


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


def _load(db: Session, record_id: uuid.UUID) -> SegmentWorkRecord:
    rec = db.get(SegmentWorkRecord, record_id)
    if rec is None or rec.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Segment work record not found")
    return rec


@router.get("", response_model=list[SegmentWorkOut])
def list_segment_work(
    project_id: Annotated[uuid.UUID, Query()],
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> list[SegmentWorkOut]:
    require_project_member(project_id, membership, user, db)
    rows = db.scalars(
        select(SegmentWorkRecord)
        .where(SegmentWorkRecord.project_id == project_id, SegmentWorkRecord.deleted_at.is_(None))
        .order_by(SegmentWorkRecord.started_at.desc())
    )
    return [_out(db, r) for r in rows]


@router.post("", response_model=SegmentWorkOut, status_code=status.HTTP_201_CREATED)
def create_segment_work(
    body: SegmentWorkCreateIn, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> SegmentWorkOut:
    project = require_project_member(body.project_id, membership, user, db)
    job_type = db.get(JobType, body.job_type_id)
    if job_type is None or job_type.organisation_id != project.organisation_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown job type")
    if body.quantity_source not in ("measured", "manual"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "quantity_source must be measured|manual")

    rec = SegmentWorkRecord(
        organisation_id=project.organisation_id,
        project_id=project.id,
        job_type_id=job_type.id,
        trail_id=body.trail_id,
        geom=_geom_expr(body.geometry),
        quantity=body.quantity or 0,
        unit=job_type.unit,
        quantity_source=body.quantity_source,
        started_at=body.started_at,
        ended_at=body.ended_at,
        active_seconds=body.active_seconds,
        pauses=body.pauses,
        crew_size=body.crew_size,
        equipment=body.equipment,
        notes=body.notes,
        created_by_id=user.id,
    )
    db.add(rec)
    db.flush()
    if body.quantity_source == "measured" and body.geometry is not None:
        measured = _measured_quantity(db, rec.id, job_type.unit)
        if measured is not None:
            rec.quantity = measured
    record_change(
        db, entity_type="segment_work", entity_id=rec.id, op="upsert",
        organisation_id=project.organisation_id, project_id=project.id, actor_id=user.id,
    )
    db.commit()
    return _out(db, _load(db, rec.id))


@router.patch("/{record_id}", response_model=SegmentWorkOut)
def update_segment_work(
    record_id: uuid.UUID,
    body: SegmentWorkUpdateIn,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> SegmentWorkOut:
    rec = _load(db, record_id)
    require_project_member(rec.project_id, membership, user, db)
    if rec.created_by_id != user.id and not is_org_admin(membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own record")

    if body.job_type_id is not None:
        jt = db.get(JobType, body.job_type_id)
        if jt is None or jt.organisation_id != rec.organisation_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown job type")
        rec.job_type_id = jt.id
        rec.unit = jt.unit
    if body.trail_id is not None:
        rec.trail_id = body.trail_id
    if body.geometry is not None:
        rec.geom = _geom_expr(body.geometry)
    if body.quantity_source is not None:
        rec.quantity_source = body.quantity_source
    if body.active_seconds is not None:
        rec.active_seconds = body.active_seconds
    if body.ended_at is not None:
        rec.ended_at = body.ended_at
    if body.pauses is not None:
        rec.pauses = body.pauses
    if body.crew_size is not None:
        rec.crew_size = body.crew_size
    if body.equipment is not None:
        rec.equipment = body.equipment
    if body.notes is not None:
        rec.notes = body.notes
    db.flush()
    if body.quantity is not None:
        rec.quantity = body.quantity
    elif rec.quantity_source == "measured" and (body.geometry is not None or body.job_type_id):
        measured = _measured_quantity(db, rec.id, rec.unit)
        if measured is not None:
            rec.quantity = measured

    record_change(
        db, entity_type="segment_work", entity_id=rec.id, op="upsert",
        organisation_id=rec.organisation_id, project_id=rec.project_id, actor_id=user.id,
    )
    db.commit()
    return _out(db, _load(db, rec.id))


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_segment_work(
    record_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> None:
    rec = _load(db, record_id)
    require_project_member(rec.project_id, membership, user, db)
    if rec.created_by_id != user.id and not is_org_admin(membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own record")
    rec.deleted_at = datetime.now(UTC)
    record_change(
        db, entity_type="segment_work", entity_id=rec.id, op="delete",
        organisation_id=rec.organisation_id, project_id=rec.project_id, actor_id=user.id,
    )
    db.commit()
    return None


# --------------------------------------------------------------------------- #
# Rollup
# --------------------------------------------------------------------------- #


@router.get("/rollup", response_model=SegmentRollupOut)
def rollup(
    project_id: Annotated[uuid.UUID, Query()],
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
    group_by: Annotated[str, Query()] = "job_type",
) -> SegmentRollupOut:
    if group_by not in _ROLLUP_DIMS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"group_by must be one of {_ROLLUP_DIMS}")
    require_project_member(project_id, membership, user, db)

    R = SegmentWorkRecord
    person_hours = func.sum(R.active_seconds / 3600.0 * R.crew_size)
    total_qty = func.sum(R.quantity)
    total_minutes = func.sum(R.active_seconds / 60.0)
    n = func.count(R.id)
    units = func.count(func.distinct(R.unit))
    any_unit = func.min(R.unit)
    base_where = [R.project_id == project_id, R.deleted_at.is_(None)]

    groups: list[SegmentRollupGroup] = []

    if group_by == "job_type":
        rows = db.execute(
            select(
                R.job_type_id, JobType.label, JobType.unit, JobType.expected_rate,
                n, total_qty, person_hours, total_minutes,
            )
            .join(JobType, JobType.id == R.job_type_id, isouter=True)
            .where(*base_where)
            .group_by(R.job_type_id, JobType.label, JobType.unit, JobType.expected_rate)
        ).all()
        for jt_id, label, unit, expected, cnt, qty, ph, mins in rows:
            groups.append(
                _group(
                    str(jt_id) if jt_id else "none",
                    label or "(no job type)",
                    unit or "",
                    cnt, qty, ph, mins, expected,
                )
            )
    else:
        if group_by == "trail":
            key_col, label_col = R.trail_id, Trail.name
            join = (Trail, Trail.id == R.trail_id)
        elif group_by == "member":
            key_col, label_col = R.created_by_id, User.name
            join = (User, User.id == R.created_by_id)
        else:  # week
            key_col = func.date_trunc("week", R.started_at)
            label_col = key_col
            join = None

        stmt = select(
            key_col, label_col, n, total_qty, person_hours, total_minutes, units, any_unit
        ).where(*base_where)
        if join is not None:
            stmt = stmt.join(join[0], join[1], isouter=True)
        stmt = stmt.group_by(key_col, label_col)
        for key, label, cnt, qty, ph, mins, distinct_units, unit in db.execute(stmt).all():
            groups.append(
                _group(
                    _key_str(key),
                    _label_str(label, group_by),
                    "mixed" if distinct_units and distinct_units > 1 else (unit or ""),
                    cnt, qty, ph, mins, None,
                )
            )

    groups.sort(key=lambda g: g.group_label)
    return SegmentRollupOut(group_by=group_by, groups=groups)


def _group(key, label, unit, count, qty, person_hours, minutes, expected) -> SegmentRollupGroup:
    qty = float(qty or 0)
    ph = round(float(person_hours or 0), 3)
    mean_rate = round(float(minutes or 0) / qty, 2) if qty > 0 else None
    delta = (
        round(mean_rate - float(expected), 2)
        if mean_rate is not None and expected is not None
        else None
    )
    return SegmentRollupGroup(
        group_key=key,
        group_label=label,
        record_count=count,
        unit=unit,
        total_quantity=round(qty, 3),
        total_person_hours=ph,
        mean_rate_min_per_unit=mean_rate,
        expected_rate=float(expected) if expected is not None else None,
        delta_min_per_unit=delta,
    )


def _key_str(key) -> str:
    if key is None:
        return "none"
    if isinstance(key, datetime):
        return key.date().isoformat()
    return str(key)


def _label_str(label, group_by: str) -> str:
    if label is None:
        return "(unassigned)" if group_by != "week" else "(no date)"
    if isinstance(label, datetime):
        return f"week of {label.date().isoformat()}"
    return str(label)
