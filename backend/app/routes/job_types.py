"""JobType taxonomy - defines how a kind of trail work is measured and,
optionally, its target rate. Org-wide (like trails); any member reads,
admin+ mutates. See docs/BLUEPRINT.md sec 10.
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
from app.models import JOB_UNITS, JobType, Membership, OrgRole
from app.schemas import JobTypeCreateIn, JobTypeOut, JobTypeUpdateIn
from app.sync import record_change

router = APIRouter(prefix="/job-types", tags=["job-types"])

DbSession = Annotated[Session, Depends(get_db)]
AdminMembership = Annotated[Membership, Depends(require_org_role(OrgRole.admin))]


def _load(db: Session, job_type_id: uuid.UUID, org_id: uuid.UUID) -> JobType:
    jt = db.get(JobType, job_type_id)
    if jt is None or jt.organisation_id != org_id or jt.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job type not found")
    return jt


@router.get("", response_model=list[JobTypeOut])
def list_job_types(
    membership: CurrentMembership,
    db: DbSession,
    activity: Annotated[str | None, Query()] = None,
) -> list[JobType]:
    stmt = select(JobType).where(
        JobType.organisation_id == membership.organisation_id, JobType.deleted_at.is_(None)
    )
    if activity is not None:
        stmt = stmt.where(JobType.activity == activity)
    return list(db.scalars(stmt.order_by(JobType.sort_group, JobType.label)))


@router.post("", response_model=JobTypeOut, status_code=status.HTTP_201_CREATED)
def create_job_type(
    body: JobTypeCreateIn, membership: AdminMembership, user: CurrentUser, db: DbSession
) -> JobType:
    if body.unit not in JOB_UNITS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unit must be one of {JOB_UNITS}")
    dup = db.scalar(
        select(JobType).where(
            JobType.organisation_id == membership.organisation_id,
            JobType.activity == body.activity,
            JobType.key == body.key,
            JobType.deleted_at.is_(None),
        )
    )
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A job type with that key already exists")

    jt = JobType(
        organisation_id=membership.organisation_id,
        activity=body.activity,
        key=body.key,
        label=body.label,
        unit=body.unit,
        default_crew=body.default_crew,
        expected_rate=body.expected_rate,
        color=body.color,
        sort_group=body.sort_group,
    )
    db.add(jt)
    db.flush()
    record_change(
        db, entity_type="job_type", entity_id=jt.id, op="upsert",
        organisation_id=jt.organisation_id, actor_id=user.id,
    )
    db.commit()
    db.refresh(jt)
    return jt


@router.patch("/{job_type_id}", response_model=JobTypeOut)
def update_job_type(
    job_type_id: uuid.UUID,
    body: JobTypeUpdateIn,
    membership: AdminMembership,
    user: CurrentUser,
    db: DbSession,
) -> JobType:
    jt = _load(db, job_type_id, membership.organisation_id)
    if body.unit is not None:
        if body.unit not in JOB_UNITS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unit must be one of {JOB_UNITS}")
        jt.unit = body.unit
    if body.label is not None:
        jt.label = body.label
    if body.default_crew is not None:
        jt.default_crew = body.default_crew
    if body.expected_rate is not None:
        jt.expected_rate = body.expected_rate
    if body.color is not None:
        jt.color = body.color
    if body.sort_group is not None:
        jt.sort_group = body.sort_group
    record_change(
        db, entity_type="job_type", entity_id=jt.id, op="upsert",
        organisation_id=jt.organisation_id, actor_id=user.id,
    )
    db.commit()
    db.refresh(jt)
    return jt


@router.delete("/{job_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_type(
    job_type_id: uuid.UUID, membership: AdminMembership, user: CurrentUser, db: DbSession
) -> None:
    jt = _load(db, job_type_id, membership.organisation_id)
    jt.deleted_at = datetime.now(UTC)
    record_change(
        db, entity_type="job_type", entity_id=jt.id, op="delete",
        organisation_id=jt.organisation_id, actor_id=user.id,
    )
    db.commit()
    return None
