"""Discussion threads: the project's own thread (task_id null) and one per
task. Append-only - messages are soft-deleted, never edited. Posting a
message fans out notification-inbox rows (see app/notifications.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import is_org_admin, require_project_member
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser
from app.models import Message, ProjectMember, Task, TaskAssignee, User
from app.notifications import notify
from app.schemas import MessageCreateIn, MessageOut
from app.sync import record_change

router = APIRouter(prefix="/messages", tags=["messages"])

DbSession = Annotated[Session, Depends(get_db)]


def _thread_where(project_id: uuid.UUID, task_id: uuid.UUID | None):
    clauses = [Message.project_id == project_id, Message.deleted_at.is_(None)]
    clauses.append(Message.task_id == task_id if task_id is not None else Message.task_id.is_(None))
    return clauses


@router.get("", response_model=list[MessageOut])
def list_messages(
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
    project_id: Annotated[uuid.UUID, Query()],
    task_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[Message]:
    require_project_member(project_id, membership, user, db)
    return list(
        db.scalars(
            select(Message)
            .where(*_thread_where(project_id, task_id))
            .order_by(Message.created_at)
        )
    )


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def create_message(
    body: MessageCreateIn, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> Message:
    project = require_project_member(body.project_id, membership, user, db)

    task = None
    if body.task_id is not None:
        task = db.get(Task, body.task_id)
        if task is None or task.project_id != project.id or task.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found in this project")

    member_ids = set(
        db.scalars(
            select(ProjectMember.user_id).where(ProjectMember.project_id == project.id)
        )
    )
    mentioned = [uid for uid in dict.fromkeys(body.mention_user_ids) if uid in member_ids]

    msg = Message(
        organisation_id=project.organisation_id,
        project_id=project.id,
        task_id=body.task_id,
        author_id=user.id,
        body=body.body,
        mentioned_user_ids=[str(uid) for uid in mentioned],
    )
    db.add(msg)
    db.flush()

    record_change(
        db, entity_type="message", entity_id=msg.id, op="upsert",
        organisation_id=project.organisation_id, project_id=project.id, actor_id=user.id,
    )
    _fan_out_notifications(db, msg, project.organisation_id, task, member_ids, set(mentioned), user)
    db.commit()
    db.refresh(msg)
    return msg


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> None:
    msg = db.get(Message, message_id)
    if msg is None or msg.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    require_project_member(msg.project_id, membership, user, db)
    if msg.author_id != user.id and not is_org_admin(membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the author or an admin can delete")
    msg.deleted_at = datetime.now(UTC)
    record_change(
        db, entity_type="message", entity_id=msg.id, op="delete",
        organisation_id=msg.organisation_id, project_id=msg.project_id, actor_id=user.id,
    )
    db.commit()
    return None


def _fan_out_notifications(
    db: Session,
    msg: Message,
    org_id: uuid.UUID,
    task: Task | None,
    member_ids: set[uuid.UUID],
    mentioned: set[uuid.UUID],
    author: User,
) -> None:
    preview = msg.body if len(msg.body) <= 120 else msg.body[:117] + "..."

    if task is not None:
        assignees = set(
            db.scalars(select(TaskAssignee.user_id).where(TaskAssignee.task_id == task.id))
        )
        prior_authors = set(
            db.scalars(
                select(Message.author_id).where(
                    Message.task_id == task.id, Message.author_id.is_not(None)
                )
            )
        )
        recipients = (assignees | prior_authors | {task.created_by_id}) - mentioned
        notify(
            db, organisation_id=org_id, recipient_ids=recipients, actor_id=author.id,
            type="task_commented", subject_type="task", subject_id=task.id,
            project_id=msg.project_id, body=f'{author.name} on "{task.title}": {preview}',
        )
    else:
        notify(
            db, organisation_id=org_id, recipient_ids=member_ids - mentioned, actor_id=author.id,
            type="project_commented", subject_type="project", subject_id=msg.project_id,
            project_id=msg.project_id, body=f"{author.name}: {preview}",
        )

    if mentioned:
        notify(
            db, organisation_id=org_id, recipient_ids=mentioned, actor_id=author.id,
            type="mention", subject_type="message", subject_id=msg.id,
            project_id=msg.project_id, body=f"{author.name} mentioned you: {preview}",
        )
