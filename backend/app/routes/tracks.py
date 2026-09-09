"""GPX tracks - routes recorded live by the field app or uploaded from a
GPX file (docs/BLUEPRINT.md sec 3, sec 15).

Project-scoped like tasks: any project member records or imports; the
recorder or an org admin edits and deletes. The full per-point detail is
kept for a faithful GPX re-export but never enters the sync stream.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

import gpxpy
import gpxpy.gpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from geoalchemy2 import Geography
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz import is_org_admin, require_project_member
from app.db import get_db
from app.deps import CurrentMembership, CurrentUser
from app.geo import linestring_wkt, to_geojson
from app.models import GpxTrack, TrackSource
from app.schemas import TrackCreateIn, TrackOut, TrackUpdateIn
from app.sync import record_change

router = APIRouter(prefix="/tracks", tags=["tracks"])

DbSession = Annotated[Session, Depends(get_db)]


def _select(where_clauses: list):
    geojson = func.ST_AsGeoJSON(GpxTrack.geom).label("geojson")
    length_m = func.ST_Length(func.cast(GpxTrack.geom, Geography)).label("length_m")
    return select(GpxTrack, geojson, length_m).where(*where_clauses)


def _out(track: GpxTrack, geojson: str, length_m: float | None) -> TrackOut:
    return TrackOut(
        id=track.id,
        organisation_id=track.organisation_id,
        project_id=track.project_id,
        name=track.name,
        activity=track.activity,
        source=track.source,
        started_at=track.started_at,
        ended_at=track.ended_at,
        moving_seconds=track.moving_seconds,
        length_m=round(length_m or 0.0, 1),
        point_count=len(track.points or []),
        geometry=to_geojson(geojson),
        recorded_by_id=track.recorded_by_id,
        created_at=track.created_at,
        updated_at=track.updated_at,
    )


def fetch_track_out(db: Session, track_id: uuid.UUID) -> TrackOut | None:
    row = db.execute(
        _select([GpxTrack.id == track_id, GpxTrack.deleted_at.is_(None)])
    ).first()
    return _out(*row) if row is not None else None


def _get_out(db: Session, track_id: uuid.UUID) -> TrackOut:
    out = fetch_track_out(db, track_id)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found")
    return out


def _load(db: Session, track_id: uuid.UUID) -> GpxTrack:
    track = db.get(GpxTrack, track_id)
    if track is None or track.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Track not found")
    return track


def _points_payload(points: list) -> list[dict]:
    """Normalise incoming points (schema objects or dicts) to plain JSON."""
    out = []
    for p in points:
        lat = getattr(p, "lat", None) if not isinstance(p, dict) else p.get("lat")
        lon = getattr(p, "lon", None) if not isinstance(p, dict) else p.get("lon")
        ele = getattr(p, "ele", None) if not isinstance(p, dict) else p.get("ele")
        t = getattr(p, "t", None) if not isinstance(p, dict) else p.get("t")
        row: dict = {"lat": float(lat), "lon": float(lon)}
        if ele is not None:
            row["ele"] = float(ele)
        if t is not None:
            row["t"] = t.isoformat() if isinstance(t, datetime) else str(t)
        out.append(row)
    return out


def _make_track(
    db: Session,
    *,
    project,
    user,
    name: str,
    activity: str,
    source: str,
    points: list[dict],
    started_at: datetime | None,
    ended_at: datetime | None,
    moving_seconds: int,
) -> GpxTrack:
    track = GpxTrack(
        organisation_id=project.organisation_id,
        project_id=project.id,
        name=name,
        activity=activity,
        source=source,
        started_at=started_at,
        ended_at=ended_at,
        moving_seconds=moving_seconds,
        geom=linestring_wkt([(p["lat"], p["lon"]) for p in points]),
        points=points,
        recorded_by_id=user.id,
    )
    db.add(track)
    db.flush()
    record_change(
        db, entity_type="track", entity_id=track.id, op="upsert",
        organisation_id=project.organisation_id, project_id=project.id, actor_id=user.id,
    )
    return track


@router.get("", response_model=list[TrackOut])
def list_tracks(
    project_id: Annotated[uuid.UUID, Query()],
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> list[TrackOut]:
    require_project_member(project_id, membership, user, db)
    rows = db.execute(
        _select([GpxTrack.project_id == project_id, GpxTrack.deleted_at.is_(None)])
        .order_by(GpxTrack.created_at.desc())
    ).all()
    return [_out(*r) for r in rows]


@router.post("", response_model=TrackOut, status_code=status.HTTP_201_CREATED)
def create_track(
    body: TrackCreateIn, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> TrackOut:
    project = require_project_member(body.project_id, membership, user, db)
    track = _make_track(
        db,
        project=project,
        user=user,
        name=body.name,
        activity=body.activity,
        source=TrackSource.recorded.value,
        points=_points_payload(body.points),
        started_at=body.started_at,
        ended_at=body.ended_at,
        moving_seconds=body.moving_seconds,
    )
    db.commit()
    return _get_out(db, track.id)


@router.post("/import-gpx", response_model=list[TrackOut], status_code=status.HTTP_201_CREATED)
async def import_gpx(
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    project_id: Annotated[uuid.UUID, Form()],
    activity: Annotated[str, Form()] = "mtb",
) -> list[TrackOut]:
    project = require_project_member(project_id, membership, user, db)
    raw = await file.read()
    try:
        gpx = gpxpy.parse(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Not a valid GPX file: {exc}") from exc

    base_name = (file.filename or "Imported track").rsplit(".", 1)[0]
    created: list[GpxTrack] = []
    for t_index, gtrack in enumerate(gpx.tracks):
        pts: list[dict] = []
        times: list[datetime] = []
        for segment in gtrack.segments:
            for p in segment.points:
                row: dict = {"lat": p.latitude, "lon": p.longitude}
                if p.elevation is not None:
                    row["ele"] = p.elevation
                if p.time is not None:
                    row["t"] = p.time.isoformat()
                    times.append(p.time)
                pts.append(row)
        if len(pts) < 2:
            continue
        name = gtrack.name or (base_name if t_index == 0 else f"{base_name} ({t_index})")
        created.append(
            _make_track(
                db,
                project=project,
                user=user,
                name=name,
                activity=activity,
                source=TrackSource.imported.value,
                points=pts,
                started_at=min(times) if times else None,
                ended_at=max(times) if times else None,
                moving_seconds=0,
            )
        )

    if not created:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "GPX file has no track with 2+ points")
    db.commit()
    return [_get_out(db, t.id) for t in created]


@router.get("/{track_id}", response_model=TrackOut)
def get_track(
    track_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> TrackOut:
    track = _load(db, track_id)
    require_project_member(track.project_id, membership, user, db)
    return _get_out(db, track_id)


@router.patch("/{track_id}", response_model=TrackOut)
def update_track(
    track_id: uuid.UUID,
    body: TrackUpdateIn,
    membership: CurrentMembership,
    user: CurrentUser,
    db: DbSession,
) -> TrackOut:
    track = _load(db, track_id)
    require_project_member(track.project_id, membership, user, db)
    if track.recorded_by_id != user.id and not is_org_admin(membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own track")
    if body.name is not None:
        track.name = body.name
    if body.activity is not None:
        track.activity = body.activity
    record_change(
        db, entity_type="track", entity_id=track.id, op="upsert",
        organisation_id=track.organisation_id, project_id=track.project_id, actor_id=user.id,
    )
    db.commit()
    return _get_out(db, track.id)


@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_track(
    track_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> None:
    track = _load(db, track_id)
    require_project_member(track.project_id, membership, user, db)
    if track.recorded_by_id != user.id and not is_org_admin(membership):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own track")
    track.deleted_at = datetime.now(UTC)
    record_change(
        db, entity_type="track", entity_id=track.id, op="delete",
        organisation_id=track.organisation_id, project_id=track.project_id, actor_id=user.id,
    )
    db.commit()
    return None


@router.get("/{track_id}/gpx")
def export_gpx(
    track_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> Response:
    track = _load(db, track_id)
    require_project_member(track.project_id, membership, user, db)

    gpx = gpxpy.gpx.GPX()
    gpx.creator = "Trailkeeper"
    gtrack = gpxpy.gpx.GPXTrack(name=track.name)
    gpx.tracks.append(gtrack)
    seg = gpxpy.gpx.GPXTrackSegment()
    gtrack.segments.append(seg)
    for p in track.points or []:
        t = p.get("t")
        seg.points.append(
            gpxpy.gpx.GPXTrackPoint(
                p["lat"],
                p["lon"],
                elevation=p.get("ele"),
                time=datetime.fromisoformat(t) if t else None,
            )
        )

    # HTTP headers are latin-1; give ASCII clients a transliterated name and
    # everyone else the real UTF-8 one (RFC 5987).
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "-", track.name).strip("-")[:60] or "track"
    disposition = (
        f'attachment; filename="{ascii_name}.gpx"; '
        f"filename*=UTF-8''{quote(track.name)}.gpx"
    )
    return Response(
        content=gpx.to_xml(),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": disposition},
    )
