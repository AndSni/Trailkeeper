from tests.conftest import auth_headers

# ~1 km at 57N: 0.009 deg of latitude.
POINTS = [
    {"lat": 57.000, "lon": 24.0, "ele": 10.0, "t": "2026-08-30T08:00:00Z"},
    {"lat": 57.003, "lon": 24.0, "ele": 12.0, "t": "2026-08-30T08:05:00Z"},
    {"lat": 57.006, "lon": 24.0, "ele": 11.0, "t": "2026-08-30T08:10:00Z"},
    {"lat": 57.009, "lon": 24.0, "ele": 9.0, "t": "2026-08-30T08:15:00Z"},
]

GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Imported loop</name><trkseg>
    <trkpt lat="57.0" lon="24.1"><ele>5</ele><time>2026-08-30T09:00:00Z</time></trkpt>
    <trkpt lat="57.004" lon="24.1"><ele>6</ele><time>2026-08-30T09:06:00Z</time></trkpt>
    <trkpt lat="57.009" lon="24.1"><time>2026-08-30T09:12:00Z</time></trkpt>
  </trkseg></trk>
</gpx>
"""


def _member(client, owner, project_id, email="m@example.com"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "editor"}
    ).json()["token"]
    tokens = client.post(
        "/auth/invite/accept",
        json={"token": token, "name": "Mo", "password": "yet another phrase"},
    ).json()
    h = auth_headers(tokens["access_token"])
    uid = client.get("/auth/me", headers=h).json()["user"]["id"]
    client.post(
        f"/projects/{project_id}/members",
        headers=owner["headers"],
        json={"user_id": uid, "project_role": "member"},
    )
    return h, uid


def _create(client, headers, project_id, **over):
    body = {
        "project_id": project_id,
        "name": "Morning brushcut route",
        "started_at": "2026-08-30T08:00:00Z",
        "ended_at": "2026-08-30T08:15:00Z",
        "moving_seconds": 780,
        "points": POINTS,
    }
    body.update(over)
    return client.post("/tracks", headers=headers, json=body)


def test_create_derives_geometry_and_length(client, owner, owner_project):
    project_id, headers = owner_project
    r = _create(client, headers, project_id)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["source"] == "recorded"
    assert t["point_count"] == 4
    assert t["geometry"]["type"] == "LineString"
    assert abs(t["length_m"] - 1000) < 40  # geography length of the ~1 km line
    assert t["moving_seconds"] == 780

    listed = client.get(f"/tracks?project_id={project_id}", headers=headers).json()
    assert [x["id"] for x in listed] == [t["id"]]


def test_needs_two_points(client, owner, owner_project):
    project_id, headers = owner_project
    assert _create(client, headers, project_id, points=POINTS[:1]).status_code == 422


def test_import_gpx(client, owner, owner_project):
    project_id, headers = owner_project
    r = client.post(
        "/tracks/import-gpx",
        headers=headers,
        files={"file": ("ride.gpx", GPX, "application/gpx+xml")},
        data={"project_id": project_id, "activity": "hike"},
    )
    assert r.status_code == 201, r.text
    tracks = r.json()
    assert len(tracks) == 1
    assert tracks[0]["name"] == "Imported loop"
    assert tracks[0]["source"] == "imported"
    assert tracks[0]["activity"] == "hike"
    assert tracks[0]["point_count"] == 3
    from datetime import datetime

    assert datetime.fromisoformat(tracks[0]["started_at"]) == datetime.fromisoformat(
        "2026-08-30T09:00:00+00:00"
    )


def test_gpx_roundtrip_export(client, owner, owner_project):
    project_id, headers = owner_project
    tid = _create(client, headers, project_id, name="Rīta brauciens").json()["id"]
    resp = client.get(f"/tracks/{tid}/gpx", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/gpx+xml")
    cd = resp.headers["content-disposition"]
    assert "attachment" in cd
    assert 'filename="R-ta-brauciens.gpx"' in cd  # ascii-safe fallback
    assert "filename*=UTF-8''" in cd  # rfc 5987 real name
    body = resp.text
    assert "<gpx" in body and "Rīta brauciens" in body
    assert body.count("<trkpt") == 4
    assert "<ele>" in body and "<time>" in body


def test_author_only_edit_and_sync(client, owner, owner_project):
    project_id, headers = owner_project
    member_h, _ = _member(client, owner, project_id)
    tid = _create(client, headers, project_id).json()["id"]

    snap = client.get(f"/sync/snapshot?project={project_id}", headers=headers).json()
    assert [t["id"] for t in snap["tracks"]] == [tid]
    assert "points" not in snap["tracks"][0]  # raw points never in sync

    changes = client.get("/sync/changes?since=0", headers=headers).json()["changes"]
    ch = next(c for c in changes if c["entity_type"] == "track" and c["entity_id"] == tid)
    assert ch["project_id"] == project_id

    assert client.patch(
        f"/tracks/{tid}", headers=member_h, json={"name": "hijack"}
    ).status_code == 403
    assert client.delete(f"/tracks/{tid}", headers=member_h).status_code == 403

    up = client.patch(f"/tracks/{tid}", headers=headers, json={"name": "Renamed"})
    assert up.status_code == 200 and up.json()["name"] == "Renamed"

    assert client.delete(f"/tracks/{tid}", headers=headers).status_code == 204
    del_ch = next(
        c
        for c in client.get("/sync/changes?since=0", headers=headers).json()["changes"]
        if c["entity_type"] == "track" and c["entity_id"] == tid
    )
    assert del_ch["op"] == "delete"
