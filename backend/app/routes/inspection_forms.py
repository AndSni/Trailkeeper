"""InspectionForm taxonomy - reusable JSON-schema questionnaires for
structure inspections. Org-wide like job types (BLUEPRINT sec 3, sec 16:
"Fixed JSON-schema forms for P5"); members read, admin+ mutates. Every edit
bumps `version` so an Inspection can pin the exact form it answered.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import CurrentMembership, CurrentUser, require_org_role
from app.models import INSPECTION_FIELD_TYPES, InspectionForm, Membership, OrgRole
from app.schemas import InspectionFormCreateIn, InspectionFormOut, InspectionFormUpdateIn
from app.sync import record_change

router = APIRouter(prefix="/inspection-forms", tags=["inspection-forms"])

DbSession = Annotated[Session, Depends(get_db)]
AdminMembership = Annotated[Membership, Depends(require_org_role(OrgRole.admin))]


def _validate_fields(fields: list) -> None:
    seen: set[str] = set()
    for i, f in enumerate(fields):
        if not isinstance(f, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"field {i} is not an object")
        key = f.get("key")
        if not isinstance(key, str) or not key.strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"field {i} needs a non-empty key")
        if key in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"duplicate field key {key!r}")
        seen.add(key)
        ftype = f.get("type")
        if ftype not in INSPECTION_FIELD_TYPES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"field {key!r} type must be one of {INSPECTION_FIELD_TYPES}",
            )
        if ftype == "choice":
            choices = f.get("choices")
            if not isinstance(choices, list) or not choices:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"choice field {key!r} needs a non-empty choices list",
                )


def _out(form: InspectionForm) -> InspectionFormOut:
    return InspectionFormOut(
        id=form.id,
        organisation_id=form.organisation_id,
        name=form.name,
        target_type=form.target_type,
        fields=form.schema_json,
        version=form.version,
        is_active=form.is_active,
        created_at=form.created_at,
        updated_at=form.updated_at,
    )


def fetch_inspection_form_out(db: Session, form_id: uuid.UUID) -> InspectionFormOut | None:
    form = db.get(InspectionForm, form_id)
    if form is None or form.deleted_at is not None:
        return None
    return _out(form)


def _load(db: Session, form_id: uuid.UUID, org_id: uuid.UUID) -> InspectionForm:
    form = db.get(InspectionForm, form_id)
    if form is None or form.organisation_id != org_id or form.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inspection form not found")
    return form


@router.get("", response_model=list[InspectionFormOut])
def list_inspection_forms(
    membership: CurrentMembership,
    db: DbSession,
    active: Annotated[bool | None, Query()] = None,
) -> list[InspectionFormOut]:
    stmt = select(InspectionForm).where(
        InspectionForm.organisation_id == membership.organisation_id,
        InspectionForm.deleted_at.is_(None),
    )
    if active is not None:
        stmt = stmt.where(InspectionForm.is_active.is_(active))
    return [_out(f) for f in db.scalars(stmt.order_by(InspectionForm.name))]


@router.post("", response_model=InspectionFormOut, status_code=status.HTTP_201_CREATED)
def create_inspection_form(
    body: InspectionFormCreateIn, membership: AdminMembership, user: CurrentUser, db: DbSession
) -> InspectionFormOut:
    _validate_fields(body.fields)
    form = InspectionForm(
        organisation_id=membership.organisation_id,
        name=body.name,
        target_type=body.target_type,
        schema_json=body.fields,
        version=1,
        is_active=body.is_active,
    )
    db.add(form)
    db.flush()
    record_change(
        db, entity_type="inspection_form", entity_id=form.id, op="upsert",
        organisation_id=form.organisation_id, actor_id=user.id,
    )
    db.commit()
    db.refresh(form)
    return _out(form)


@router.patch("/{form_id}", response_model=InspectionFormOut)
def update_inspection_form(
    form_id: uuid.UUID,
    body: InspectionFormUpdateIn,
    membership: AdminMembership,
    user: CurrentUser,
    db: DbSession,
) -> InspectionFormOut:
    form = _load(db, form_id, membership.organisation_id)
    if body.fields is not None:
        _validate_fields(body.fields)
        form.schema_json = body.fields
    if body.name is not None:
        form.name = body.name
    if body.target_type is not None:
        form.target_type = body.target_type
    if body.is_active is not None:
        form.is_active = body.is_active
    form.version += 1
    record_change(
        db, entity_type="inspection_form", entity_id=form.id, op="upsert",
        organisation_id=form.organisation_id, actor_id=user.id,
    )
    db.commit()
    db.refresh(form)
    return _out(form)


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inspection_form(
    form_id: uuid.UUID, membership: AdminMembership, user: CurrentUser, db: DbSession
) -> None:
    form = _load(db, form_id, membership.organisation_id)
    form.deleted_at = datetime.now(UTC)
    record_change(
        db, entity_type="inspection_form", entity_id=form.id, op="delete",
        organisation_id=form.organisation_id, actor_id=user.id,
    )
    db.commit()
    return None
