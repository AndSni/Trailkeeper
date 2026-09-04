from tests.conftest import auth_headers


def _invite_member(client, owner, project_id, email="m@example.com"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "editor"}
    ).json()["token"]
    tokens = client.post(
        "/auth/invite/accept",
        json={"token": token, "name": "Crew Member", "password": "yet another phrase"},
    ).json()
    me = client.get("/auth/me", headers=auth_headers(tokens["access_token"])).json()
    uid = me["user"]["id"]
    client.post(
        f"/projects/{project_id}/members",
        headers=owner["headers"],
        json={"user_id": uid, "project_role": "member"},
    )
    return auth_headers(tokens["access_token"]), uid


def test_create_and_list_work_log(client, owner, owner_project):
    project_id, headers = owner_project
    resp = client.post(
        f"/work-logs?project_id={project_id}",
        headers=headers,
        json={"minutes": 90, "worked_on": "2026-08-30", "note": "brushcutting"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["auto_from_task"] is False

    listed = client.get(f"/work-logs?project_id={project_id}", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["minutes"] == 90


def test_member_can_only_edit_own_log(client, owner, owner_project):
    project_id, headers = owner_project
    member_headers, _uid = _invite_member(client, owner, project_id)

    log_id = client.post(
        f"/work-logs?project_id={project_id}",
        headers=member_headers,
        json={"minutes": 30, "worked_on": "2026-08-30"},
    ).json()["id"]

    # Another plain member can't edit someone else's log...
    other_headers, _ = _invite_member(client, owner, project_id, email="other@example.com")
    assert client.patch(
        f"/work-logs/{log_id}", headers=other_headers, json={"minutes": 999}
    ).status_code == 403

    # ...but the org owner (admin+) can.
    admin_patch = client.patch(f"/work-logs/{log_id}", headers=headers, json={"minutes": 45})
    assert admin_patch.status_code == 200
    assert admin_patch.json()["minutes"] == 45

    # The original author can edit their own.
    own_patch = client.patch(f"/work-logs/{log_id}", headers=member_headers, json={"minutes": 60})
    assert own_patch.status_code == 200
    assert own_patch.json()["minutes"] == 60


def test_delete_work_log(client, owner, owner_project):
    project_id, headers = owner_project
    log_id = client.post(
        f"/work-logs?project_id={project_id}",
        headers=headers,
        json={"minutes": 15, "worked_on": "2026-08-30"},
    ).json()["id"]
    assert client.delete(f"/work-logs/{log_id}", headers=headers).status_code == 204
    assert client.get(f"/work-logs?project_id={project_id}", headers=headers).json() == []


def test_visibility_requires_project_membership(client, owner, owner_project):
    project_id, headers = owner_project

    # An org member who was never added to this project - not the same as
    # not being logged in at all.
    token = client.post(
        "/org/invites",
        headers=owner["headers"],
        json={"email": "outsider@example.com", "org_role": "editor"},
    ).json()["token"]
    outsider_headers = auth_headers(
        client.post(
            "/auth/invite/accept",
            json={"token": token, "name": "Outsider", "password": "yet another phrase"},
        ).json()["access_token"]
    )

    resp = client.get(f"/work-logs?project_id={project_id}", headers=outsider_headers)
    assert resp.status_code == 404
