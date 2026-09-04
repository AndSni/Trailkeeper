from tests.conftest import auth_headers

_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test">
  <trk>
    <name>Ridge Loop</name>
    <trkseg>
      <trkpt lat="57.0000" lon="24.0000"><ele>10</ele></trkpt>
      <trkpt lat="57.0010" lon="24.0010"><ele>12</ele></trkpt>
      <trkpt lat="57.0020" lon="24.0005"><ele>15</ele></trkpt>
    </trkseg>
  </trk>
</gpx>
"""


def _invite_editor(client, owner, email="ed@example.com"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "editor"}
    ).json()["token"]
    tokens = client.post(
        "/auth/invite/accept",
        json={"token": token, "name": "Ed Editor", "password": "yet another phrase"},
    ).json()
    return auth_headers(tokens["access_token"])


def test_create_trail_returns_geojson_and_length(client, owner):
    resp = client.post(
        "/trails",
        headers=owner["headers"],
        json={
            "name": "Ridge Loop",
            "activity": "mtb",
            "points": [[57.0, 24.0], [57.001, 24.001], [57.002, 24.0005]],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["geometry"]["type"] == "LineString"
    assert len(body["geometry"]["coordinates"]) == 3
    assert body["length_m"] > 0
    assert body["source"] == "drawn"


def test_editor_cannot_create_trail(client, owner):
    editor_headers = _invite_editor(client, owner)
    resp = client.post(
        "/trails",
        headers=editor_headers,
        json={"name": "Nope", "points": [[57.0, 24.0], [57.001, 24.001]]},
    )
    assert resp.status_code == 403


def test_any_member_can_list_trails(client, owner):
    client.post(
        "/trails",
        headers=owner["headers"],
        json={"name": "Ridge Loop", "points": [[57.0, 24.0], [57.001, 24.001]]},
    )
    editor_headers = _invite_editor(client, owner)
    listed = client.get("/trails", headers=editor_headers).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "Ridge Loop"


def test_update_and_soft_delete_trail(client, owner):
    tid = client.post(
        "/trails",
        headers=owner["headers"],
        json={"name": "Ridge Loop", "points": [[57.0, 24.0], [57.001, 24.001]]},
    ).json()["id"]

    patched = client.patch(f"/trails/{tid}", headers=owner["headers"], json={"status": "closed"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "closed"

    assert client.delete(f"/trails/{tid}", headers=owner["headers"]).status_code == 204
    assert client.get("/trails", headers=owner["headers"]).json() == []
    assert client.get(f"/trails/{tid}", headers=owner["headers"]).status_code == 404


def test_import_gpx_creates_trail_from_track(client, owner):
    resp = client.post(
        "/trails/import-gpx",
        headers=owner["headers"],
        files={"file": ("ridge.gpx", _GPX.encode(), "application/gpx+xml")},
        data={"activity": "hiking"},
    )
    assert resp.status_code == 201, resp.text
    trails = resp.json()
    assert len(trails) == 1
    assert trails[0]["name"] == "Ridge Loop"
    assert trails[0]["source"] == "imported"
    assert trails[0]["activity"] == "hiking"
    assert trails[0]["geometry"]["type"] == "LineString"
    assert len(trails[0]["geometry"]["coordinates"]) == 3


def test_import_bad_gpx_is_400(client, owner):
    resp = client.post(
        "/trails/import-gpx",
        headers=owner["headers"],
        files={"file": ("bad.gpx", b"not xml at all", "application/gpx+xml")},
    )
    assert resp.status_code == 400
