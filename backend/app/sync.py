"""The write half of sync: `record_change` appends one `change_log` row per
mutation, in the caller's transaction. Every mutating route calls it right
before `db.commit()`. Kept as an explicit call rather than a Session event
hook so the audit trail is greppable and there are no flush-order surprises
(see docs/BLUEPRINT.md sec 8).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import ChangeLog


def record_change(
    db: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    op: str,
    organisation_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    project_id: uuid.UUID | None = None,
) -> ChangeLog:
    """Append one change_log row. Returns it so callers that need the
    assigned `server_seq` (e.g. /sync/push) can `db.flush()` and read it."""
    cl = ChangeLog(
        organisation_id=organisation_id,
        entity_type=entity_type,
        entity_id=entity_id,
        op=op,
        project_id=project_id,
        actor_id=actor_id,
    )
    db.add(cl)
    return cl
