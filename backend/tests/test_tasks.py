from tests.conftest import auth_headers


def _create_trail(client, owner, points=None):
    points = points or [[57.0, 24.0], [57.001, 24.001], [57.002, 24.0005]]
    return client.post(
        "/trails", headers=owner["headers"], json={"name": "Ridge Loop", "points": points}
    ).json()["id"]


def _invite_member(client, owner, project_id, email="m@example.com", project_role="member"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "editor"}
    ).json()["token"]
    tokens = client.post(
        "/auth/invite/accept",
        json={"token": token, "name": "Crew Member", "password": "yet another phrase"},
    ).json()
    me = client.get("/auth/me", headers=auth_headers(tokens["access_token"])).json()
    uid = me["user"]["id"]
    add = client.post(
        f"/projects/{project_id}/members",
        headers=owner["headers"],
        json={"user_id": uid, "project_role": project_role},
    )
    assert add.status_code == 201, add.text
    return auth_headers(tokens["access_token"]), uid


def test_create_task_with_point_attaches_nearest_trail(client, owner, owner_project):
    project_id, headers = owner_project
    _create_trail(client, owner)  # runs through (57.000,24.000) -> (57.002,24.0005)

    resp = client.post(
        f"/tasks?project_id={project_id}",
        headers=headers,
        json={"title": "Fix waterbar", "lat": 57.0005, "lon": 24.0005, "priority": "high"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["geometry"] == {"type": "Point", "coordinates": [24.0005, 57.0005]}
    assert body["nearest_trail_id"] is not None
    assert body["status"] == "open"
    assert body["photos"] == []
    assert body["assignee_ids"] == []


def test_create_task_far_from_any_trail_has_no_nearest(client, owner, owner_project):
    project_id, headers = owner_project
    _create_trail(client, owner)
    resp = client.post(
        f"/tasks?project_id={project_id}",
        headers=headers,
        # ~11km away - well past nearest_trail_max_m
        json={"title": "Far away", "lat": 57.1, "lon": 24.1},
    )
    assert resp.status_code == 201
    assert resp.json()["nearest_trail_id"] is None


def test_task_visibility_follows_project_membership(client, owner, owner_project):
    project_id, headers = owner_project
    tid = client.post(
        f"/tasks?project_id={project_id}", headers=headers, json={"title": "Only members see"}
    ).json()["id"]
    assert client.get(f"/tasks/{tid}", headers=headers).status_code == 200

    # An org member invited but never added to *this* project can't reach it.
    token = client.post(
        "/org/invites",
        headers=owner["headers"],
        json={"email": "outside@example.com", "org_role": "editor"},
    ).json()["token"]
    outsider = auth_headers(
        client.post(
            "/auth/invite/accept",
            json={"token": token, "name": "Outside", "password": "yet another phrase"},
        ).json()["access_token"]
    )
    assert client.get(f"/tasks/{tid}", headers=outsider).status_code == 404
    assert client.get(f"/tasks?project_id={project_id}", headers=outsider).status_code == 404

    # Once added, they can.
    member_headers, _uid = _invite_member(client, owner, project_id, email="inside@example.com")
    assert client.get(f"/tasks/{tid}", headers=member_headers).status_code == 200


def test_assignees_and_photo_and_complete_flow(client, owner, owner_project):
    project_id, headers = owner_project
    member_headers, member_id = _invite_member(client, owner, project_id)

    tid = client.post(
        f"/tasks?project_id={project_id}",
        headers=headers,
        json={"title": "Clear blowdown", "estimate_min": 45},
    ).json()["id"]

    assigned = client.put(
        f"/tasks/{tid}/assignees", headers=headers, json={"user_ids": [member_id]}
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignee_ids"] == [member_id]

    # A tiny valid PNG (1x1, transparent).
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000a49444154789c6360000002000100"
        "5a5a5a5a0000000049454e44ae426082"
    )
    photo = client.post(
        f"/tasks/{tid}/photos",
        headers=member_headers,
        files={"file": ("blowdown.png", png_bytes, "image/png")},
        data={"caption": "before"},
    )
    assert photo.status_code == 201, photo.text
    assert photo.json()["caption"] == "before"
    photo_id = photo.json()["id"]

    fetched = client.get(f"/tasks/{tid}/photos/{photo_id}/file", headers=member_headers)
    assert fetched.status_code == 200
    assert fetched.content == png_bytes

    done = client.post(f"/tasks/{tid}/complete", headers=member_headers, json={})
    assert done.status_code == 200
    assert done.json()["status"] == "done"

    logs = client.get(f"/work-logs?project_id={project_id}", headers=headers).json()
    assert len(logs) == 1
    assert logs[0]["minutes"] == 45
    assert logs[0]["auto_from_task"] is True
    assert logs[0]["task_id"] == tid

    assert client.delete(f"/tasks/{tid}/photos/{photo_id}", headers=headers).status_code == 204
    assert client.get(f"/tasks/{tid}/photos/{photo_id}/file", headers=headers).status_code == 404


def test_upload_rejects_non_image(client, owner, owner_project):
    project_id, headers = owner_project
    tid = client.post(
        f"/tasks?project_id={project_id}", headers=headers, json={"title": "T"}
    ).json()["id"]
    resp = client.post(
        f"/tasks/{tid}/photos",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_complete_without_estimate_or_minutes_logs_nothing(client, owner, owner_project):
    project_id, headers = owner_project
    tid = client.post(
        f"/tasks?project_id={project_id}", headers=headers, json={"title": "No estimate"}
    ).json()["id"]
    client.post(f"/tasks/{tid}/complete", headers=headers, json={})
    logs = client.get(f"/work-logs?project_id={project_id}", headers=headers).json()
    assert logs == []
