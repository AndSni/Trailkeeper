from tests.conftest import auth_headers

# A ~1 km trail near (57.0, 24.0) so a structure placed on it auto-attaches.
TRAIL_LINE = [[57.0, 24.0], [57.009, 24.0]]


def _viewer(client, owner, email="v@example.com"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "viewer"}
    ).json()["token"]
    return auth_headers(
        client.post(
            "/auth/invite/accept",
            json={"token": token, "name": "Vi", "password": "yet another phrase"},
        ).json()["access_token"]
    )


def _trail(client, owner):
    return client.post(
        "/trails",
        headers=owner["headers"],
        json={"name": "Ridge", "points": TRAIL_LINE},
    ).json()["id"]


def test_create_lists_and_auto_attaches(client, owner):
    trail_id = _trail(client, owner)
    r = client.post(
        "/structures",
        headers=owner["headers"],
        json={
            "name": "Ridge culvert",
            "structure_type": "culvert",
            "lat": 57.004,
            "lon": 24.0,
            "material": "HDPE",
            "inspection_interval_days": 365,
        },
    )
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["structure_type"] == "culvert"
    assert s["status"] == "good"
    assert s["geometry"]["type"] == "Point"
    assert s["nearest_trail_id"] == trail_id

    listed = client.get("/structures", headers=owner["headers"]).json()
    assert [x["id"] for x in listed] == [s["id"]]
    by_trail = client.get(f"/structures?trail_id={trail_id}", headers=owner["headers"]).json()
    assert len(by_trail) == 1
    by_type = client.get("/structures?type=bridge", headers=owner["headers"]).json()
    assert by_type == []


def test_patch_and_soft_delete(client, owner):
    sid = client.post(
        "/structures",
        headers=owner["headers"],
        json={"name": "Sign 4", "structure_type": "sign", "color": "#B7791F"},
    ).json()["id"]

    up = client.patch(
        f"/structures/{sid}",
        headers=owner["headers"],
        json={"status": "needs_repair", "notes": "post rotten", "name": "Sign 4A", "color": "#2E7D32"},
    )
    assert up.status_code == 200
    assert up.json()["status"] == "needs_repair"
    assert up.json()["name"] == "Sign 4A"
    assert up.json()["color"] == "#2E7D32"

    assert client.delete(f"/structures/{sid}", headers=owner["headers"]).status_code == 204
    assert client.get(f"/structures/{sid}", headers=owner["headers"]).status_code == 404
    assert sid not in {x["id"] for x in client.get("/structures", headers=owner["headers"]).json()}


def test_viewer_cannot_mutate_but_can_read(client, owner):
    viewer = _viewer(client, owner)
    assert (
        client.post(
            "/structures", headers=viewer, json={"name": "x", "structure_type": "gate"}
        ).status_code
        == 403
    )
    assert client.get("/structures", headers=viewer).status_code == 200


def test_syncs_org_wide(client, owner, owner_project):
    project_id, headers = owner_project
    sid = client.post(
        "/structures", headers=headers, json={"name": "Bridge 1", "structure_type": "bridge"}
    ).json()["id"]

    snap = client.get(f"/sync/snapshot?project={project_id}", headers=headers).json()
    assert [s["id"] for s in snap["structures"]] == [sid]

    changes = client.get("/sync/changes?since=0", headers=headers).json()["changes"]
    change = next(c for c in changes if c["entity_type"] == "structure" and c["entity_id"] == sid)
    assert change["project_id"] is None  # org-wide, like trails
    assert change["op"] == "upsert"
