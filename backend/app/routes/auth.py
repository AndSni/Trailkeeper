"""Registration, login, token refresh, invite acceptance, /auth/me."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import CurrentUser
from app.models import Invite, Membership, Organisation, OrgRole, User
from app.schemas import (
    AcceptInviteIn,
    LoginIn,
    MembershipOut,
    MeOut,
    RefreshIn,
    RegisterIn,
    TokenPair,
    UserOut,
)
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]


def _tokens(user_id: uuid.UUID) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


def _user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: DbSession) -> TokenPair:
    """Bootstrap: create the first user and their organisation (as owner).

    Disabled once `allow_registration` is turned off; further members then
    join via an invite only.
    """
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Open registration is disabled")
    if _user_by_email(db, body.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    org = Organisation(name=body.organisation_name)
    user = User(email=body.email, name=body.name, password_hash=hash_password(body.password))
    db.add_all([org, user])
    db.flush()
    db.add(Membership(organisation_id=org.id, user_id=user.id, org_role=OrgRole.owner.value))
    db.commit()
    return _tokens(user.id)


@router.post("/login", response_model=TokenPair)
def login(body: LoginIn, db: DbSession) -> TokenPair:
    user = _user_by_email(db, body.email)
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _tokens(user.id)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshIn, db: DbSession) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return _tokens(user.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(_user: CurrentUser) -> None:
    # Tokens are stateless in Phase 0; the client drops them. A deny-list /
    # rotation store lands with the sync work in Phase 2.
    return None


@router.post("/invite/accept", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def accept_invite(body: AcceptInviteIn, db: DbSession) -> TokenPair:
    invite = db.scalar(select(Invite).where(Invite.token == body.token))
    if invite is None or invite.accepted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found or already used")
    if invite.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "Invite has expired")

    user = _user_by_email(db, invite.email)
    if user is None:
        user = User(
            email=invite.email, name=body.name, password_hash=hash_password(body.password)
        )
        db.add(user)
        db.flush()

    already = db.scalar(
        select(Membership).where(
            Membership.organisation_id == invite.organisation_id,
            Membership.user_id == user.id,
        )
    )
    if already is None:
        db.add(
            Membership(
                organisation_id=invite.organisation_id,
                user_id=user.id,
                org_role=invite.org_role,
            )
        )
    invite.accepted_at = datetime.now(UTC)
    db.commit()
    return _tokens(user.id)


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, db: DbSession) -> MeOut:
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id))
    return MeOut(
        user=UserOut.model_validate(user),
        memberships=[MembershipOut.model_validate(m) for m in memberships],
    )


def make_invite_token() -> str:
    return secrets.token_urlsafe(32)
