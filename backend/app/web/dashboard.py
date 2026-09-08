"""Read-only dashboard aggregates for the web console. Every number here is
computed straight from the same tables the API writes; nothing is cached
yet (BLUEPRINT sec 11 - caching + exports land in the next P6 slice).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Inspection,
    JobType,
    Membership,
    Organisation,
    Project,
    ProjectMember,
    SegmentWorkRecord,
    Structure,
    Task,
    User,
    WorkLog,
)


def _project_cards(db: Session, org_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(
        select(Project)
        .where(Project.organisation_id == org_id, Project.deleted_at.is_(None))
        .order_by(Project.created_at.desc())
    ).all()
    cards = []
    for p in rows:
        open_n = db.scalar(
            select(func.count(Task.id)).where(
                Task.project_id == p.id, Task.deleted_at.is_(None), Task.status != "done"
            )
        )
        done_n = db.scalar(
            select(func.count(Task.id)).where(
                Task.project_id == p.id, Task.deleted_at.is_(None), Task.status == "done"
            )
        )
        members_n = db.scalar(
            select(func.count(ProjectMember.id)).where(ProjectMember.project_id == p.id)
        )
        cards.append(
            {
                "id": str(p.id),
                "name": p.name,
                "status": p.status,
                "open": open_n or 0,
                "done": done_n or 0,
                "members": members_n or 0,
            }
        )
    return cards


def _hours_per_member(db: Session, project_id: uuid.UUID) -> list[dict]:
    """WorkLog minutes + SegmentWorkRecord person-hours, per member, for one
    project. Two separate group-bys folded together by user id."""
    logged = dict(
        db.execute(
            select(WorkLog.user_id, func.coalesce(func.sum(WorkLog.minutes), 0))
            .where(WorkLog.project_id == project_id)
            .group_by(WorkLog.user_id)
        ).all()
    )
    segments = dict(
        db.execute(
            select(
                SegmentWorkRecord.created_by_id,
                func.coalesce(
                    func.sum(
                        SegmentWorkRecord.active_seconds / 3600.0 * SegmentWorkRecord.crew_size
                    ),
                    0.0,
                ),
            )
            .where(
                SegmentWorkRecord.project_id == project_id,
                SegmentWorkRecord.deleted_at.is_(None),
            )
            .group_by(SegmentWorkRecord.created_by_id)
        ).all()
    )
    user_ids = {uid for uid in (*logged, *segments) if uid is not None}
    if not user_ids:
        return []
    names = dict(
        db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all()
    )
    out = []
    for uid in user_ids:
        log_h = round((logged.get(uid, 0) or 0) / 60.0, 1)
        seg_h = round(float(segments.get(uid, 0.0) or 0.0), 1)
        out.append(
            {
                "name": names.get(uid, "Unknown"),
                "logged_hours": log_h,
                "segment_hours": seg_h,
                "total_hours": round(log_h + seg_h, 1),
            }
        )
    out.sort(key=lambda r: r["total_hours"], reverse=True)
    return out


def _job_type_productivity(db: Session, project_id: uuid.UUID) -> list[dict]:
    R = SegmentWorkRecord
    rows = db.execute(
        select(
            JobType.label,
            JobType.unit,
            JobType.expected_rate,
            func.count(R.id),
            func.coalesce(func.sum(R.quantity), 0),
            func.coalesce(func.sum(R.active_seconds / 3600.0 * R.crew_size), 0.0),
            func.coalesce(func.sum(R.active_seconds / 60.0), 0.0),
        )
        .join(JobType, JobType.id == R.job_type_id, isouter=True)
        .where(R.project_id == project_id, R.deleted_at.is_(None))
        .group_by(JobType.label, JobType.unit, JobType.expected_rate)
    ).all()
    out = []
    for label, unit, expected, n, qty, person_h, minutes in rows:
        qty = float(qty or 0)
        mean_rate = round(float(minutes or 0) / qty, 1) if qty > 0 else None
        expected_f = float(expected) if expected is not None else None
        delta = (
            round(mean_rate - expected_f, 1)
            if mean_rate is not None and expected_f is not None
            else None
        )
        out.append(
            {
                "label": label or "(no job type)",
                "unit": unit or "",
                "records": n,
                "quantity": round(qty, 2),
                "person_hours": round(float(person_h or 0), 1),
                "mean_rate": mean_rate,
                "expected_rate": expected_f,
                "delta": delta,
            }
        )
    out.sort(key=lambda r: r["label"])
    return out


def _task_status_counts(db: Session, project_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(Task.status, func.count(Task.id))
        .where(Task.project_id == project_id, Task.deleted_at.is_(None))
        .group_by(Task.status)
    ).all()
    return {status: n for status, n in rows}


def _structure_status_counts(db: Session, org_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(Structure.status, func.count(Structure.id))
        .where(Structure.organisation_id == org_id, Structure.deleted_at.is_(None))
        .group_by(Structure.status)
    ).all()
    return {status: n for status, n in rows}


def _recent_inspections(db: Session, org_id: uuid.UUID, limit: int = 8) -> list[dict]:
    rows = db.execute(
        select(Inspection, Structure.name, User.name)
        .join(Structure, Structure.id == Inspection.structure_id)
        .join(User, User.id == Inspection.inspector_id, isouter=True)
        .where(Inspection.organisation_id == org_id, Inspection.deleted_at.is_(None))
        .order_by(Inspection.inspected_on.desc(), Inspection.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "structure": s_name,
            "inspector": u_name or "Unknown",
            "on": insp.inspected_on.isoformat(),
            "risk": insp.risk,
            "condition": insp.condition,
        }
        for insp, s_name, u_name in rows
    ]


def gather(db: Session, membership: Membership, project_id: str | None) -> dict:
    org = db.get(Organisation, membership.organisation_id)
    member_count = db.scalar(
        select(func.count(Membership.id)).where(
            Membership.organisation_id == membership.organisation_id
        )
    )
    projects = _project_cards(db, membership.organisation_id)

    selected = None
    if project_id:
        selected = next((p for p in projects if p["id"] == project_id), None)
    if selected is None and projects:
        selected = next((p for p in projects if p["status"] == "active"), projects[0])

    ctx: dict = {
        "org_name": org.name if org else "",
        "member_count": member_count or 0,
        "projects": projects,
        "selected": selected,
        "structure_status": _structure_status_counts(db, membership.organisation_id),
        "recent_inspections": _recent_inspections(db, membership.organisation_id),
    }
    if selected is not None:
        pid = uuid.UUID(selected["id"])
        ctx["task_status"] = _task_status_counts(db, pid)
        ctx["hours_per_member"] = _hours_per_member(db, pid)
        ctx["job_productivity"] = _job_type_productivity(db, pid)
    else:
        ctx["task_status"] = {}
        ctx["hours_per_member"] = []
        ctx["job_productivity"] = []
    return ctx
