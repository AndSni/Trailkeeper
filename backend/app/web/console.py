"""Web console routes - server-rendered HTML, no JS build. The browser
session is the refresh-token JWT in an HttpOnly `tk_session` cookie; console
routes load the user straight from the DB rather than calling the JSON API.
Registration / login / invite-accept reuse the exact `app.routes.auth`
handlers so there's one code path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Invite, Membership, Organisation, OrgRole, User
from app.routes.auth import accept_invite as api_accept_invite
from app.routes.auth import login as api_login
from app.routes.auth import register as api_register
from app.routes.org import create_invite as api_create_invite
from app.schemas import AcceptInviteIn, InviteIn, LoginIn, RegisterIn
from app.security import decode_token
from app.web.dashboard import gather
from app.web.exports import DATASETS, csv_bytes, photo_zip_bytes, workbook_bytes

router = APIRouter(tags=["console"], include_in_schema=False)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

DbSession = Annotated[Session, Depends(get_db)]
SESSION_COOKIE = "tk_session"


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #


def _set_session(resp: RedirectResponse, request: Request, refresh_token: str) -> None:
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    resp.set_cookie(
        SESSION_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        samesite="lax",
        secure=https,
        path="/",
    )


def _redirect(to: str) -> RedirectResponse:
    return RedirectResponse(to, status_code=status.HTTP_303_SEE_OTHER)


class NeedsLogin(Exception):
    pass


def current_identity(request: Request, db: DbSession) -> tuple[User, Membership]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise NeedsLogin
    try:
        payload = decode_token(token, expected_type="refresh")
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise NeedsLogin from None
    if user is None or not user.is_active:
        raise NeedsLogin
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    if membership is None:
        raise NeedsLogin
    return user, membership


Identity = Annotated[tuple[User, Membership], Depends(current_identity)]


def _optional_identity(request: Request, db: Session) -> tuple[User, Membership] | None:
    try:
        return current_identity(request, db)
    except NeedsLogin:
        return None


# --------------------------------------------------------------------------- #
# Auth pages
# --------------------------------------------------------------------------- #


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: DbSession):
    return _redirect("/app" if _optional_identity(request, db) else "/login")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: DbSession):
    if _optional_identity(request, db):
        return _redirect("/app")
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    db: DbSession,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    try:
        pair = api_login(LoginIn(email=email, password=password), db)
    except HTTPException:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid email or password"}, status_code=200
        )
    resp = _redirect("/app")
    _set_session(resp, request, pair.refresh_token)
    return resp


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: DbSession):
    if _optional_identity(request, db):
        return _redirect("/app")
    return templates.TemplateResponse(
        request,
        "register.html",
        {"error": None, "disabled": not settings.allow_registration},
    )


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    db: DbSession,
    organisation_name: Annotated[str, Form()],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    try:
        body = RegisterIn(
            organisation_name=organisation_name, name=name, email=email, password=password
        )
    except ValueError:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Check the fields - password must be at least 8 characters.",
             "disabled": not settings.allow_registration},
            status_code=200,
        )
    try:
        pair = api_register(body, db)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": exc.detail, "disabled": not settings.allow_registration},
            status_code=200,
        )
    resp = _redirect("/app")
    _set_session(resp, request, pair.refresh_token)
    return resp


@router.get("/invite/{token}", response_class=HTMLResponse)
def invite_page(token: str, request: Request, db: DbSession):
    invite = db.scalar(select(Invite).where(Invite.token == token))
    valid = (
        invite is not None
        and invite.accepted_at is None
        and invite.expires_at >= datetime.now(UTC)
    )
    org_name = None
    if valid:
        org = db.get(Organisation, invite.organisation_id)
        org_name = org.name if org else None
    return templates.TemplateResponse(
        request,
        "invite.html",
        {
            "token": token,
            "valid": valid,
            "email": invite.email if invite else None,
            "org_name": org_name,
            "error": None,
        },
    )


@router.post("/invite/{token}", response_class=HTMLResponse)
def invite_submit(
    token: str,
    request: Request,
    db: DbSession,
    name: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    try:
        pair = api_accept_invite(AcceptInviteIn(token=token, name=name, password=password), db)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "invite.html",
            {"token": token, "valid": True, "email": None, "org_name": None,
             "error": exc.detail},
            status_code=200,
        )
    resp = _redirect("/app")
    _set_session(resp, request, pair.refresh_token)
    return resp


@router.get("/logout")
def logout(request: Request):
    resp = _redirect("/login")
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #


@router.get("/app", response_class=HTMLResponse)
def dashboard(request: Request, identity: Identity, db: DbSession, project: str | None = None):
    user, membership = identity
    ctx = gather(db, membership, project)
    ctx.update(
        user_name=user.name,
        org_role=membership.org_role,
        is_admin=OrgRole(membership.org_role) in (OrgRole.owner, OrgRole.admin),
        active="dashboard",
    )
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@router.get("/app/members", response_class=HTMLResponse)
def members_page(request: Request, identity: Identity, db: DbSession, invited: str | None = None):
    user, membership = identity
    if OrgRole(membership.org_role) not in (OrgRole.owner, OrgRole.admin):
        return _redirect("/app")

    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organisation_id == membership.organisation_id)
        .order_by(User.name)
    ).all()
    pending = db.scalars(
        select(Invite)
        .where(
            Invite.organisation_id == membership.organisation_id,
            Invite.accepted_at.is_(None),
        )
        .order_by(Invite.created_at.desc())
    ).all()
    org = db.get(Organisation, membership.organisation_id)
    base = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        request,
        "members.html",
        {
            "org_name": org.name if org else "",
            "members": [
                {"name": u.name, "email": u.email, "role": m.org_role} for m, u in rows
            ],
            "pending": [
                {
                    "email": iv.email,
                    "role": iv.org_role,
                    "link": f"{base}/invite/{iv.token}",
                    "expires": iv.expires_at.date().isoformat(),
                }
                for iv in pending
            ],
            "invited_link": f"{base}/invite/{invited}" if invited else None,
            "roles": [r.value for r in OrgRole],
            "is_admin": True,
            "active": "members",
        },
    )


@router.post("/app/invites")
def members_invite(
    request: Request,
    identity: Identity,
    db: DbSession,
    email: Annotated[str, Form()],
    org_role: Annotated[str, Form()] = "editor",
):
    user, membership = identity
    if OrgRole(membership.org_role) not in (OrgRole.owner, OrgRole.admin):
        return _redirect("/app")
    try:
        invite = api_create_invite(
            InviteIn(email=email, org_role=OrgRole(org_role)), membership, user, db
        )
    except (HTTPException, ValueError):
        return _redirect("/app/members")
    return _redirect(f"/app/members?invited={invite.token}")


# --------------------------------------------------------------------------- #
# Exports (BLUEPRINT sec 11)
# --------------------------------------------------------------------------- #


def _selected_project_id(db: Session, membership: Membership, project: str | None) -> str | None:
    ctx = gather(db, membership, project)
    return ctx["selected"]["id"] if ctx["selected"] else None


@router.get("/app/export/{dataset}.csv")
def export_csv(
    dataset: str, identity: Identity, db: DbSession, project: str | None = None
):
    _user, membership = identity
    if dataset not in DATASETS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown dataset")
    pid = _selected_project_id(db, membership, project)
    payload = csv_bytes(db, membership, uuid.UUID(pid) if pid else None, dataset)
    return Response(
        content=payload,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="trailkeeper-{dataset}.csv"'},
    )


@router.get("/app/export.xlsx")
def export_workbook(
    identity: Identity, db: DbSession, project: str | None = None
):
    _user, membership = identity
    pid = _selected_project_id(db, membership, project)
    payload = workbook_bytes(db, membership, uuid.UUID(pid) if pid else None)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="trailkeeper-export.xlsx"'},
    )


@router.get("/app/export/photos.zip")
def export_photos(identity: Identity, db: DbSession, project: str | None = None):
    _user, membership = identity
    pid = _selected_project_id(db, membership, project)
    payload = photo_zip_bytes(db, membership, uuid.UUID(pid) if pid else None)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="trailkeeper-photos.zip"'},
    )
