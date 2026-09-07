"""The per-user notification inbox + FCM device registration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import CurrentUser
from app.models import DeviceToken, Notification
from app.schemas import DeviceRegisterIn, NotificationOut, NotificationReadIn

router = APIRouter(tags=["notifications"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    user: CurrentUser,
    db: DbSession,
    unread: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Notification]:
    stmt = select(Notification).where(Notification.recipient_id == user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit)))


@router.get("/notifications/unread-count")
def unread_count(user: CurrentUser, db: DbSession) -> dict:
    n = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
    )
    return {"count": n or 0}


@router.post("/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(body: NotificationReadIn, user: CurrentUser, db: DbSession) -> None:
    stmt = (
        update(Notification)
        .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    if not body.all:
        stmt = stmt.where(Notification.id.in_(body.ids))
    db.execute(stmt)
    db.commit()
    return None


@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT)
def register_device(body: DeviceRegisterIn, user: CurrentUser, db: DbSession) -> None:
    existing = db.scalar(select(DeviceToken).where(DeviceToken.fcm_token == body.fcm_token))
    if existing is None:
        db.add(
            DeviceToken(
                user_id=user.id,
                fcm_token=body.fcm_token,
                platform=body.platform,
                app_version=body.app_version,
            )
        )
    else:
        existing.user_id = user.id
        existing.platform = body.platform
        existing.app_version = body.app_version
        existing.last_seen_at = datetime.now(UTC)
    db.commit()
    return None
