"""Inspection capture - one filled-in InspectionForm against one Structure,
recorded in a project's context (BLUEPRINT sec 3). Any project member
records one; the author or an org admin edits or deletes it. An inspection
may carry a `condition` that writes back to the structure's status.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import is_org_admin, require_project_member
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser
from app.models import Inspection, InspectionForm, Structure
from app.schemas import InspectionCreateIn, InspectionOut, InspectionUpdateIn
from app.sync import record_change

router = APIRouter(prefix="/inspections", tags=["inspections"])

DbSession = Annotated[Session, Depends(get_db)]


def _out(rec: Inspection) -> InspectionOut:
    return InspectionOut(
        id=rec.id,
        organisation_id=rec.organisation_id,
        project_id=rec.project_id,
        structure_id=rec.structure_id,
        form_id=rec.form_id,
        form_version=rec.form_version,
        inspector_id=rec.inspector_id,
        inspected_on=rec.inspected_on,
        answers=rec.answers,
        risk=rec.risk,
        condition=rec.condition,
        notes=rec.notes,
        created_by_id=rec.created_by_id,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def fetch_inspection_out(db: Session, inspection_id: uuid.UUID) -> InspectionOut | None:
    rec = db.get(Inspection, inspection_id)
    if rec is None or rec.deleted_at is not None:
        return None
    return _out(rec)


def _load(db: Session, inspection_id: uuid.UUID) -> Inspection:
    rec = db.get(Inspection, inspection_id)
    if rec is None or rec.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inspection not found")
    return rec


def _apply_condition(db: Session, rec: Inspection, actor_id: uuid.UUID) -> None:
    """If the inspection set a condition, write it to the structure's status
    and log a structure change so the map/list reflects it."""
    if rec.condition is None:
        return
    structure = db.get(Structure, rec.structure_id)
    if structure is None or structure.deleted_at is not None:
        return
    if structure.status == rec.condition:
        return
    structure.status = rec.condition
    record_change(
        db, entity_type="structure", entity_id=structure.id, op="upsert",
        organisation_id=structure.organisation_id, actor_id=actor_id,
    )


@router.get("", response_model=list[InspectionOut])
def list_inspections(
    project_id: Annotated[uuid.UUID, Query()],
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
    structure_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[InspectionOut]:
    require_project_member(project_id, membership, user, db)
    where = [Inspection.project_id == project_id, Inspection.deleted_at.is_(None)]
    if structure_id is not None:
        where.append(Inspection.structure_id == structure_id)
    rows = db.scalars(
        select(Inspection).where(*where).order_by(Inspection.inspected_on.desc())
    )
    return [_out(r) for r in rows]


@router.post("", response_model=InspectionOut, status_code=status.HTTP_201_CREATED)
def create_inspection(
    body: InspectionCreateIn, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> InspectionOut:
    project = require_project_member(body.project_id, membership, user, db)

    structure = db.get(Structure, body.structure_id)
    if (
        structure is None
        or structure.organisation_id != project.organisation_id
        or structure.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown structure")

    form_version = None
    if body.form_id is not None:
        form = db.get(InspectionForm, body.form_id)
        if (
            form is None
            or form.organisation_id != project.organisation_id
            or form.deleted_at is not None
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown inspection form")
        form_version = form.version

    rec = Inspection(
        organisation_id=project.organisation_id,
        project_id=project.id,
        structure_id=structure.id,
        form_id=body.form_id,
        form_version=form_version,
        inspector_id=user.id,
        inspected_on=body.inspected_on or date.today(),
        answers=body.answers,
        risk=body.risk.value if body.risk is not None else None,
        condition=body.condition.value if body.condition is not None else None,
        notes=body.notes,
        created_by_id=user.id,
    )
    db.add(rec)
    db.flush()
    _apply_condition(db, rec, user.id)
    record_change(
        db, entity_type="inspection", entity_id=rec.id, op="upsert",
        organisation_id=rec.organisation_id, project_id=rec.project_id, actor_id=user.id,
    )
    db.commit()
    return _out(_load(db, rec.id))


@router.patch("/{inspection_id}", response_model=InspectionOut)
def update_inspection(
    inspection_id: uuid.UUID,
    body: InspectionUpdateIn,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> InspectionOut:
    rec = _load(db, inspection_id)
    require_project_member(rec.project_id, membership, user, db)
    if rec.created_by_id != user.id and not is_org_admin(membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own inspection")

    if body.inspected_on is not None:
        rec.inspected_on = body.inspected_on
    if body.answers is not None:
        rec.answers = body.answers
    if body.risk is not None:
        rec.risk = body.risk.value
    if body.notes is not None:
        rec.notes = body.notes
    if body.condition is not None:
        rec.condition = body.condition.value
        _apply_condition(db, rec, user.id)

    record_change(
        db, entity_type="inspection", entity_id=rec.id, op="upsert",
        organisation_id=rec.organisation_id, project_id=rec.project_id, actor_id=user.id,
    )
    db.commit()
    return _out(_load(db, rec.id))


@router.delete("/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inspection(
    inspection_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> None:
    rec = _load(db, inspection_id)
    require_project_member(rec.project_id, membership, user, db)
    if rec.created_by_id != user.id and not is_org_admin(membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own inspection")
    rec.deleted_at = datetime.now(UTC)
    record_change(
        db, entity_type="inspection", entity_id=rec.id, op="delete",
        organisation_id=rec.organisation_id, project_id=rec.project_id, actor_id=user.id,
    )
    db.commit()
    return None
