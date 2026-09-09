"""CSV / XLSX exports for the web console (BLUEPRINT sec 11). Each dataset is
a (title, header, row-builder) triple; CSV serves one, the workbook serves
all of them, one sheet each. Everything is computed live from the same
tables the API writes - no caching yet.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Inspection,
    JobType,
    Membership,
    SegmentWorkRecord,
    Structure,
    Task,
    TaskAssignee,
    TaskPhoto,
    Trail,
    User,
)
from app.web.dashboard import _hours_per_member, _job_type_productivity

Row = list[object]
RowBuilder = Callable[[Session, Membership, uuid.UUID | None], list[Row]]


def _hours_rows(db: Session, membership: Membership, project_id: uuid.UUID | None) -> list[Row]:
    if project_id is None:
        return []
    return [
        [r["name"], r["logged_hours"], r["segment_hours"], r["total_hours"]]
        for r in _hours_per_member(db, project_id)
    ]


def _productivity_rows(
    db: Session, membership: Membership, project_id: uuid.UUID | None
) -> list[Row]:
    if project_id is None:
        return []
    return [
        [
            r["label"], r["unit"], r["records"], r["quantity"], r["person_hours"],
            r["mean_rate"], r["expected_rate"], r["delta"],
        ]
        for r in _job_type_productivity(db, project_id)
    ]


def _task_rows(db: Session, membership: Membership, project_id: uuid.UUID | None) -> list[Row]:
    if project_id is None:
        return []
    rows = db.execute(
        select(Task, Trail.name)
        .join(Trail, Trail.id == Task.nearest_trail_id, isouter=True)
        .where(Task.project_id == project_id, Task.deleted_at.is_(None))
        .order_by(Task.created_at.desc())
    ).all()
    out: list[Row] = []
    for task, trail_name in rows:
        assignees = db.scalars(
            select(User.name)
            .join(TaskAssignee, TaskAssignee.user_id == User.id)
            .where(TaskAssignee.task_id == task.id)
        ).all()
        out.append(
            [
                task.title, task.task_type, task.priority, task.status,
                task.estimate_min, "; ".join(assignees), trail_name or "",
                task.created_at.isoformat(),
            ]
        )
    return out


def _segment_rows(db: Session, membership: Membership, project_id: uuid.UUID | None) -> list[Row]:
    if project_id is None:
        return []
    R = SegmentWorkRecord
    rows = db.execute(
        select(R, JobType.label, User.name)
        .join(JobType, JobType.id == R.job_type_id, isouter=True)
        .join(User, User.id == R.created_by_id, isouter=True)
        .where(R.project_id == project_id, R.deleted_at.is_(None))
        .order_by(R.started_at.desc())
    ).all()
    out: list[Row] = []
    for rec, label, who in rows:
        qty = float(rec.quantity)
        person_h = round(rec.active_seconds / 3600 * rec.crew_size, 2)
        rate = round((rec.active_seconds / 60) / qty, 2) if qty > 0 else None
        out.append(
            [
                label or "", rec.started_at.isoformat(), qty, rec.unit,
                rec.active_seconds, rec.crew_size, person_h, rate,
                ", ".join(rec.equipment or []), rec.notes, who or "",
            ]
        )
    return out


def _structure_rows(
    db: Session, membership: Membership, project_id: uuid.UUID | None
) -> list[Row]:
    rows = db.execute(
        select(Structure, Trail.name)
        .join(Trail, Trail.id == Structure.nearest_trail_id, isouter=True)
        .where(
            Structure.organisation_id == membership.organisation_id,
            Structure.deleted_at.is_(None),
        )
        .order_by(Structure.name)
    ).all()
    return [
        [
            s.name, s.structure_type, s.status, s.material, trail_name or "",
            s.installed_on.isoformat() if s.installed_on else "", s.notes,
        ]
        for s, trail_name in rows
    ]


def _inspection_rows(
    db: Session, membership: Membership, project_id: uuid.UUID | None
) -> list[Row]:
    rows = db.execute(
        select(Inspection, Structure.name, Structure.structure_type, User.name)
        .join(Structure, Structure.id == Inspection.structure_id)
        .join(User, User.id == Inspection.inspector_id, isouter=True)
        .where(
            Inspection.organisation_id == membership.organisation_id,
            Inspection.deleted_at.is_(None),
        )
        .order_by(Inspection.inspected_on.desc(), Inspection.created_at.desc())
    ).all()
    return [
        [
            insp.inspected_on.isoformat(), s_name, s_type, who or "",
            insp.risk or "", insp.condition or "", insp.form_version or "",
            insp.notes,
        ]
        for insp, s_name, s_type, who in rows
    ]


# dataset key -> (sheet title, header, row builder, is_project_scoped)
DATASETS: dict[str, tuple[str, list[str], RowBuilder, bool]] = {
    "hours": (
        "Hours",
        ["Member", "Logged hours", "Timed-segment hours", "Total hours"],
        _hours_rows,
        True,
    ),
    "productivity": (
        "Productivity",
        ["Job type", "Unit", "Records", "Quantity", "Person-hours",
         "Mean rate (min/unit)", "Target rate", "Delta"],
        _productivity_rows,
        True,
    ),
    "tasks": (
        "Tasks",
        ["Title", "Type", "Priority", "Status", "Estimate (min)", "Assignees",
         "Nearest trail", "Created"],
        _task_rows,
        True,
    ),
    "segments": (
        "Segments",
        ["Job type", "Started", "Quantity", "Unit", "Active seconds", "Crew",
         "Person-hours", "Rate (min/unit)", "Equipment", "Notes", "By"],
        _segment_rows,
        True,
    ),
    "structures": (
        "Structures",
        ["Name", "Type", "Status", "Material", "Nearest trail", "Installed",
         "Notes"],
        _structure_rows,
        False,
    ),
    "inspections": (
        "Inspections",
        ["Date", "Structure", "Structure type", "Inspector", "Risk",
         "Condition set", "Form version", "Notes"],
        _inspection_rows,
        False,
    ),
}


def csv_bytes(db: Session, membership: Membership, project_id: uuid.UUID | None, key: str) -> bytes:
    title, header, builder, _scoped = DATASETS[key]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in builder(db, membership, project_id):
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue().encode("utf-8")


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:40] or fallback


def photo_zip_bytes(
    db: Session, membership: Membership, project_id: uuid.UUID | None
) -> bytes:
    """A zip of one project's task photos plus a manifest.csv. Photos are
    small and few per project, so this is built in memory."""
    manifest = io.StringIO()
    writer = csv.writer(manifest)
    writer.writerow(
        ["task", "task_status", "caption", "uploaded_by", "uploaded_at", "file", "note"]
    )

    rows: list = []
    if project_id is not None:
        rows = db.execute(
            select(TaskPhoto, Task, User.name)
            .join(Task, Task.id == TaskPhoto.task_id)
            .join(User, User.id == TaskPhoto.uploaded_by_id, isouter=True)
            .where(Task.project_id == project_id, Task.deleted_at.is_(None))
            .order_by(Task.title, TaskPhoto.created_at)
        ).all()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        seen: dict[str, int] = {}
        for photo, task, who in rows:
            ext = Path(photo.storage_path).suffix or ".jpg"
            folder = f"{_slug(task.title, 'task')}-{str(task.id)[:8]}"
            seen[folder] = seen.get(folder, 0) + 1
            arcname = f"photos/{folder}/{seen[folder]:02d}{ext}"

            src = Path(settings.upload_dir) / photo.storage_path
            note = ""
            if src.is_file():
                zf.write(src, arcname)
            else:
                note = "file missing on disk"
            writer.writerow(
                [
                    task.title, task.status, photo.caption, who or "",
                    photo.created_at.isoformat(),
                    arcname if not note else "", note,
                ]
            )
        zf.writestr("manifest.csv", manifest.getvalue())
    return buf.getvalue()


def workbook_bytes(
    db: Session, membership: Membership, project_id: uuid.UUID | None
) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    bold = Font(bold=True)
    for title, header, builder, _scoped in DATASETS.values():
        ws = wb.create_sheet(title=title)
        ws.append(header)
        for cell in ws[1]:
            cell.font = bold
        for row in builder(db, membership, project_id):
            ws.append(["" if v is None else v for v in row])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
