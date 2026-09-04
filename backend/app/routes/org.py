"""Organisation settings, members and invites."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser, require_org_role
from app.models import Invite, Membership, Organisation, OrgRole, User
from app.routes.auth import make_invite_token
from app.schemas import (
    InviteIn,
    InviteOut,
    MemberRoleIn,
    OrgMemberOut,
    OrgOut,
    OrgUpdateIn,
)

router = APIRouter(prefix="/org", tags=["org"])

DbSession = Annotated[Session, Depends(get_db)]
AdminMembership = Annotated[Membership, Depends(require_org_role(OrgRole.admin))]


@router.get("", response_model=OrgOut)
def get_org(membership: CurrentMembership, db: DbSession) -> Organisation:
    return db.get(Organisation, membership.organisation_id)


@router.patch("", response_model=OrgOut)
def update_org(body: OrgUpdateIn, membership: AdminMembership, db: DbSession) -> Organisation:
    org = db.get(Organisation, membership.organisation_id)
    if body.name is not None:
        org.name = body.name
    if body.timezone is not None:
        org.timezone = body.timezone
    db.commit()
    db.refresh(org)
    return org


@router.get("/members", response_model=list[OrgMemberOut])
def list_members(membership: CurrentMembership, db: DbSession) -> list[OrgMemberOut]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organisation_id == membership.organisation_id)
        .order_by(User.name)
    ).all()
    return [
        OrgMemberOut(user_id=u.id, email=u.email, name=u.name, org_role=OrgRole(m.org_role))
        for m, u in rows
    ]


@router.patch("/members/{user_id}", response_model=OrgMemberOut)
def set_member_role(
    user_id: uuid.UUID, body: MemberRoleIn, membership: AdminMembership, db: DbSession
) -> OrgMemberOut:
    target = db.scalar(
        select(Membership).where(
            Membership.organisation_id == membership.organisation_id,
            Membership.user_id == user_id,
        )
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if OrgRole(target.org_role) is OrgRole.owner and body.org_role is not OrgRole.owner:
        if _count_owners(db, membership.organisation_id) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Cannot demote the last owner")
    target.org_role = body.org_role.value
    db.commit()
    user = db.get(User, user_id)
    return OrgMemberOut(user_id=user.id, email=user.email, name=user.name, org_role=body.org_role)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: uuid.UUID, membership: AdminMembership, user: CurrentUser, db: DbSession
) -> None:
    if user_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot remove yourself")
    target = db.scalar(
        select(Membership).where(
            Membership.organisation_id == membership.organisation_id,
            Membership.user_id == user_id,
        )
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if (
        OrgRole(target.org_role) is OrgRole.owner
        and _count_owners(db, membership.organisation_id) <= 1
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot remove the last owner")
    db.delete(target)
    db.commit()
    return None


@router.get("/invites", response_model=list[InviteOut])
def list_invites(membership: AdminMembership, db: DbSession) -> list[Invite]:
    return list(
        db.scalars(
            select(Invite)
            .where(
                Invite.organisation_id == membership.organisation_id,
                Invite.accepted_at.is_(None),
            )
            .order_by(Invite.created_at.desc())
        )
    )


@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    body: InviteIn, membership: AdminMembership, user: CurrentUser, db: DbSession
) -> Invite:
    invite = Invite(
        organisation_id=membership.organisation_id,
        email=str(body.email),
        org_role=body.org_role.value,
        token=make_invite_token(),
        invited_by_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.invite_ttl_days),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    # Phase 0 has no mailer: the caller relays the token out-of-band.
    return invite


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(invite_id: uuid.UUID, membership: AdminMembership, db: DbSession) -> None:
    invite = db.scalar(
        select(Invite).where(
            Invite.id == invite_id,
            Invite.organisation_id == membership.organisation_id,
        )
    )
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")
    db.delete(invite)
    db.commit()
    return None


def _count_owners(db: Session, org_id: uuid.UUID) -> int:
    return len(
        list(
            db.scalars(
                select(Membership).where(
                    Membership.organisation_id == org_id,
                    Membership.org_role == OrgRole.owner.value,
                )
            )
        )
    )
