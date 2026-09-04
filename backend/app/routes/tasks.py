"""Task CRUD, assignees, photos, and one-tap completion.

Any project member may create, edit, complete and photograph tasks - that's
the crew's day-to-day work (see docs/BLUEPRINT.md sec 13: "Editor: in own
projects"). Only project *membership* is admin/lead-gated (routes/projects.py).

A task's `project_id` is looked up from the task itself for every route
except create/list (where the caller is choosing which project), so most
URLs need only the task's own id - no repeated project_id query params.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz import require_project_member
from app.config import settings
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser
from app.geo import find_nearest_trail, point_wkt, to_geojson
from app.models import Project, Task, TaskAssignee, TaskPhoto, TaskStatus, WorkLog
from app.schemas import (
    TaskAssigneesIn,
    TaskCompleteIn,
    TaskCreateIn,
    TaskOut,
    TaskPhotoOut,
    TaskUpdateIn,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])

DbSession = Annotated[Session, Depends(get_db)]


def _select_tasks(where_clauses: list):
    geojson = func.ST_AsGeoJSON(Task.geom).label("geojson")
    return select(Task, geojson).where(*where_clauses)


def _photo_out(photo: TaskPhoto) -> TaskPhotoOut:
    return TaskPhotoOut(
        id=photo.id,
        task_id=photo.task_id,
        caption=photo.caption,
        uploaded_by_id=photo.uploaded_by_id,
        created_at=photo.created_at,
        url=f"/tasks/{photo.task_id}/photos/{photo.id}/file",
    )


def _task_out(db: Session, task: Task, geojson: str | None) -> TaskOut:
    assignee_ids = list(
        db.scalars(select(TaskAssignee.user_id).where(TaskAssignee.task_id == task.id))
    )
    photos = db.scalars(
        select(TaskPhoto).where(TaskPhoto.task_id == task.id).order_by(TaskPhoto.created_at)
    )
    return TaskOut(
        id=task.id,
        organisation_id=task.organisation_id,
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        priority=task.priority,
        status=task.status,
        geometry=to_geojson(geojson),
        nearest_trail_id=task.nearest_trail_id,
        estimate_min=task.estimate_min,
        created_by_id=task.created_by_id,
        assignee_ids=assignee_ids,
        photos=[_photo_out(p) for p in photos],
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _get_out(db: Session, task_id: uuid.UUID) -> TaskOut:
    row = db.execute(_select_tasks([Task.id == task_id, Task.deleted_at.is_(None)])).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    task, geojson = row
    return _task_out(db, task, geojson)


def _load_visible_task(
    db: Session, task_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser
) -> tuple[Task, Project]:
    """Loads a task and checks the caller can see its project - the one
    membership check every task route (besides create/list) needs."""
    task = db.get(Task, task_id)
    if task is None or task.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    project = require_project_member(task.project_id, membership, user, db)
    return task, project


def _set_assignees(db: Session, task_id: uuid.UUID, user_ids: list[uuid.UUID]) -> None:
    db.execute(TaskAssignee.__table__.delete().where(TaskAssignee.task_id == task_id))
    for uid in dict.fromkeys(user_ids):  # de-dupe, keep order
        db.add(TaskAssignee(task_id=task_id, user_id=uid))


@router.get("", response_model=list[TaskOut])
def list_tasks(
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
    project_id: Annotated[uuid.UUID, Query()],
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
) -> list[TaskOut]:
    require_project_member(project_id, membership, user, db)
    where = [Task.project_id == project_id, Task.deleted_at.is_(None)]
    if status_filter is not None:
        where.append(Task.status == status_filter.value)
    rows = db.execute(_select_tasks(where).order_by(Task.created_at.desc())).all()
    return [_task_out(db, t, gj) for t, gj in rows]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    body: TaskCreateIn,
    project_id: Annotated[uuid.UUID, Query()],
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> TaskOut:
    project = require_project_member(project_id, membership, user, db)

    geom = None
    nearest_trail_id = None
    if body.lat is not None and body.lon is not None:
        geom = point_wkt(body.lat, body.lon)
        nearest = find_nearest_trail(
            db, project.organisation_id, body.lat, body.lon, settings.nearest_trail_max_m
        )
        if nearest is not None:
            nearest_trail_id = nearest[0]

    task = Task(
        organisation_id=project.organisation_id,
        project_id=project.id,
        title=body.title,
        description=body.description,
        task_type=body.task_type,
        priority=body.priority.value,
        geom=geom,
        nearest_trail_id=nearest_trail_id,
        estimate_min=body.estimate_min,
        created_by_id=user.id,
    )
    db.add(task)
    db.flush()
    if body.assignee_ids:
        _set_assignees(db, task.id, body.assignee_ids)
    db.commit()
    return _get_out(db, task.id)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> TaskOut:
    _load_visible_task(db, task_id, membership, user)
    return _get_out(db, task_id)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: uuid.UUID,
    body: TaskUpdateIn,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> TaskOut:
    task, project = _load_visible_task(db, task_id, membership, user)

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.task_type is not None:
        task.task_type = body.task_type
    if body.priority is not None:
        task.priority = body.priority.value
    if body.status is not None:
        task.status = body.status.value
    if body.estimate_min is not None:
        task.estimate_min = body.estimate_min
    if body.lat is not None and body.lon is not None:
        task.geom = point_wkt(body.lat, body.lon)
        nearest = find_nearest_trail(
            db, project.organisation_id, body.lat, body.lon, settings.nearest_trail_max_m
        )
        task.nearest_trail_id = nearest[0] if nearest is not None else None

    db.commit()
    return _get_out(db, task.id)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> None:
    task, _project = _load_visible_task(db, task_id, membership, user)
    task.deleted_at = datetime.now(UTC)
    db.commit()
    return None


@router.put("/{task_id}/assignees", response_model=TaskOut)
def set_assignees(
    task_id: uuid.UUID,
    body: TaskAssigneesIn,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> TaskOut:
    task, _project = _load_visible_task(db, task_id, membership, user)
    _set_assignees(db, task.id, body.user_ids)
    db.commit()
    return _get_out(db, task.id)


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(
    task_id: uuid.UUID,
    body: TaskCompleteIn,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> TaskOut:
    """One-tap "Mark done" (mirrors Trail Sentinel 1.6.0): flips status and,
    if there's a duration to log (the request's minutes, else the task's own
    estimate), auto-creates a WorkLog for whoever completed it."""
    task, project = _load_visible_task(db, task_id, membership, user)

    task.status = TaskStatus.done.value
    minutes = body.minutes if body.minutes is not None else task.estimate_min
    if minutes:
        db.add(
            WorkLog(
                organisation_id=project.organisation_id,
                project_id=project.id,
                task_id=task.id,
                user_id=user.id,
                minutes=minutes,
                worked_on=date.today(),
                note="Auto-logged on task completion",
                auto_from_task=True,
            )
        )
    db.commit()
    return _get_out(db, task.id)


_IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}


@router.post(
    "/{task_id}/photos", response_model=TaskPhotoOut, status_code=status.HTTP_201_CREATED
)
async def upload_photo(
    task_id: uuid.UUID,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    caption: Annotated[str, Form()] = "",
) -> TaskPhotoOut:
    task, _project = _load_visible_task(db, task_id, membership, user)

    ext = _IMAGE_EXTENSIONS.get(file.content_type or "")
    if ext is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported image type: {file.content_type}. Use jpeg/png/webp/heic.",
        )
    raw = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Photo exceeds the {settings.max_upload_mb} MB limit",
        )

    relative_path = f"{task.organisation_id}/{task.id}/{uuid.uuid4().hex}{ext}"
    full_path = Path(settings.upload_dir) / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(raw)

    photo = TaskPhoto(
        task_id=task.id, storage_path=relative_path, caption=caption, uploaded_by_id=user.id
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return _photo_out(photo)


@router.get("/{task_id}/photos/{photo_id}/file")
def get_photo_file(
    task_id: uuid.UUID,
    photo_id: uuid.UUID,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> FileResponse:
    task, _project = _load_visible_task(db, task_id, membership, user)
    photo = db.get(TaskPhoto, photo_id)
    if photo is None or photo.task_id != task.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    full_path = Path(settings.upload_dir) / photo.storage_path
    if not full_path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo file missing on disk")
    return FileResponse(full_path)


@router.delete("/{task_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(
    task_id: uuid.UUID,
    photo_id: uuid.UUID,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> None:
    task, _project = _load_visible_task(db, task_id, membership, user)
    photo = db.get(TaskPhoto, photo_id)
    if photo is None or photo.task_id != task.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    full_path = Path(settings.upload_dir) / photo.storage_path
    db.delete(photo)
    db.commit()
    full_path.unlink(missing_ok=True)
    return None
