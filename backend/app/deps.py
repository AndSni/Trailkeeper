"""Shared FastAPI dependencies: auth, current org membership, role gates."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Membership, OrgRole, User
from app.security import decode_token

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTH
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise _UNAUTH from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _UNAUTH
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_membership(
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    x_org_id: Annotated[str | None, Header()] = None,
) -> Membership:
    """Resolve which organisation this request acts on.

    Phase 0 is single-org, but the schema is multi-org ready. If the user
    belongs to exactly one org, use it. Otherwise an X-Org-Id header selects.
    """
    memberships = list(db.scalars(select(Membership).where(Membership.user_id == user.id)))
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No organisation membership"
        )

    if x_org_id is not None:
        try:
            wanted = uuid.UUID(x_org_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Bad X-Org-Id"
            ) from None
        for m in memberships:
            if m.organisation_id == wanted:
                return m
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of that organisation",
        )

    if len(memberships) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multiple organisations - supply an X-Org-Id header",
        )
    return memberships[0]


CurrentMembership = Annotated[Membership, Depends(get_current_membership)]

_ROLE_RANK = {OrgRole.viewer: 0, OrgRole.editor: 1, OrgRole.admin: 2, OrgRole.owner: 3}


def require_org_role(minimum: OrgRole):
    """Dependency factory: 403 unless the caller's org role is >= minimum."""

    def _dep(membership: CurrentMembership) -> Membership:
        if _ROLE_RANK[OrgRole(membership.org_role)] < _ROLE_RANK[minimum]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum.value} role or higher",
            )
        return membership

    return _dep
