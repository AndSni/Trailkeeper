from tests.conftest import auth_headers


def _mk_trail(client, owner):
    return client.post(
        "/trails",
        headers=owner["headers"],
        json={"name": "Ridge Loop", "points": [[57.0, 24.0], [57.001, 24.001]]},
    ).json()["id"]


def _invite_org_editor(client, owner, email="out@example.com"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "editor"}
    ).json()["token"]
    return auth_headers(
        client.post(
            "/auth/invite/accept",
            json={"token": token, "name": "Out", "password": "yet another phrase"},
        ).json()["access_token"]
    )


def test_changes_since_zero_returns_everything_with_rows(client, owner, owner_project):
    project_id, headers = owner_project
    trail_id = _mk_trail(client, owner)
    task_id = client.post(
        f"/tasks?project_id={project_id}",
        headers=headers,
        json={"title": "Fix waterbar", "estimate_min": 20},
    ).json()["id"]

    res = client.get("/sync/changes?since=0", headers=headers).json()
    by_type = {c["entity_type"]: c for c in res["changes"]}
    assert set(by_type) >= {"project", "trail", "task"}
    assert by_type["trail"]["row"]["id"] == trail_id
    assert by_type["trail"]["row"]["geometry"]["type"] == "LineString"
    assert by_type["task"]["row"]["id"] == task_id
    assert by_type["task"]["op"] == "upsert"
    assert res["high_seq"] > 0
    assert res["has_more"] is False

    # Cursor advanced -> nothing new.
    empty = client.get(f"/sync/changes?since={res['high_seq']}", headers=headers).json()
    assert empty["changes"] == []
    assert empty["high_seq"] == res["high_seq"]


def test_delete_shows_as_delete_with_null_row(client, owner, owner_project):
    project_id, headers = owner_project
    task_id = client.post(
        f"/tasks?project_id={project_id}", headers=headers, json={"title": "Doomed"}
    ).json()["id"]
    cursor = client.get("/sync/changes?since=0", headers=headers).json()["high_seq"]

    client.delete(f"/tasks/{task_id}", headers=headers)
    res = client.get(f"/sync/changes?since={cursor}", headers=headers).json()
    task_change = next(c for c in res["changes"] if c["entity_type"] == "task")
    assert task_change["op"] == "delete"
    assert task_change["row"] is None


def test_changes_collapse_to_latest_state(client, owner, owner_project):
    project_id, headers = owner_project
    task_id = client.post(
        f"/tasks?project_id={project_id}", headers=headers, json={"title": "v1"}
    ).json()["id"]
    cursor = client.get("/sync/changes?since=0", headers=headers).json()["high_seq"]

    client.patch(f"/tasks/{task_id}", headers=headers, json={"title": "v2"})
    client.patch(f"/tasks/{task_id}", headers=headers, json={"title": "v3", "priority": "urgent"})

    res = client.get(f"/sync/changes?since={cursor}", headers=headers).json()
    task_changes = [c for c in res["changes"] if c["entity_type"] == "task"]
    assert len(task_changes) == 1
    assert task_changes[0]["row"]["title"] == "v3"
    assert task_changes[0]["row"]["priority"] == "urgent"


def test_visibility_org_trails_yes_other_project_tasks_no(client, owner, owner_project):
    project_id, headers = owner_project
    trail_id = _mk_trail(client, owner)
    client.post(f"/tasks?project_id={project_id}", headers=headers, json={"title": "Secret"})

    outsider = _invite_org_editor(client, owner)
    res = client.get("/sync/changes?since=0", headers=outsider).json()
    types = {c["entity_type"] for c in res["changes"]}
    assert "trail" in types  # project_id is null -> always visible
    assert "task" not in types
    assert "project" not in types
    trail_change = next(c for c in res["changes"] if c["entity_type"] == "trail")
    assert trail_change["row"]["id"] == trail_id


def test_snapshot_bundles_the_project(client, owner, owner_project):
    project_id, headers = owner_project
    _mk_trail(client, owner)
    client.post(
        f"/tasks?project_id={project_id}",
        headers=headers,
        json={"title": "T", "estimate_min": 10},
    )
    client.post(
        f"/work-logs?project_id={project_id}",
        headers=headers,
        json={"minutes": 30, "worked_on": "2026-08-30"},
    )

    snap = client.get(f"/sync/snapshot?project={project_id}", headers=headers).json()
    assert snap["project"]["id"] == project_id
    assert len(snap["members"]) == 1
    assert len(snap["trails"]) == 1
    assert len(snap["tasks"]) == 1
    assert len(snap["work_logs"]) == 1
    assert snap["high_seq"] > 0

    # From the snapshot cursor onward there's nothing new.
    after = client.get(f"/sync/changes?since={snap['high_seq']}", headers=headers).json()
    assert after["changes"] == []


def test_snapshot_404_for_invisible_project(client, owner, owner_project):
    project_id, _ = owner_project
    outsider = _invite_org_editor(client, owner)
    assert client.get(f"/sync/snapshot?project={project_id}", headers=outsider).status_code == 404
