"""Creating notification-inbox rows, and (eventually) FCM push.

`notify()` just adds `Notification` rows in the caller's transaction. Push
dispatch is a best-effort no-op until a Firebase project exists for
Trailkeeper: set `firebase_credentials_path` to a real service-account file
and fill in `_send_push` with `firebase_admin.messaging` (the pattern is
lifted from SharpRight's app/notifications.py).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models import Notification

log = logging.getLogger("trailkeeper.notifications")


def notify(
    db: Session,
    *,
    organisation_id: uuid.UUID,
    recipient_ids: Iterable[uuid.UUID],
    type: str,
    subject_type: str,
    subject_id: uuid.UUID,
    body: str,
    actor_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> None:
    """Add one inbox row per recipient (de-duped, never to the actor)."""
    for rid in {r for r in recipient_ids if r is not None and r != actor_id}:
        db.add(
            Notification(
                organisation_id=organisation_id,
                recipient_id=rid,
                type=type,
                subject_type=subject_type,
                subject_id=subject_id,
                project_id=project_id,
                actor_id=actor_id,
                body=body[:500],
            )
        )


def _send_push(tokens: list[str], title: str, body: str) -> None:  # pragma: no cover
    # TODO: firebase_admin.messaging.send_each(...) once a Firebase project
    # and service-account credentials are set up for Trailkeeper.
    log.debug("push (noop): %d tokens, %s", len(tokens), title)
