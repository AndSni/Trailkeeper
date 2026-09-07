from tests.conftest import auth_headers


def _member(client, owner, project_id, email="m@example.com"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "editor"}
    ).json()["token"]
    tokens = client.post(
        "/auth/invite/accept",
        json={"token": token, "name": "Mo Member", "password": "yet another phrase"},
    ).json()
    h = auth_headers(tokens["access_token"])
    uid = client.get("/auth/me", headers=h).json()["user"]["id"]
    client.post(
        f"/projects/{project_id}/members",
        headers=owner["headers"],
        json={"user_id": uid, "project_role": "member"},
    )
    return h, uid


def _unread(client, headers) -> int:
    return client.get("/notifications/unread-count", headers=headers).json()["count"]


def test_assignment_and_comment_notify_the_right_people(client, owner, owner_project):
    project_id, owner_h = owner_project
    member_h, member_id = _member(client, owner, project_id)

    task_id = client.post(
        f"/tasks?project_id={project_id}",
        headers=owner_h,
        json={"title": "Fix the gate", "assignee_ids": [member_id]},
    ).json()["id"]

    # The assignee got a task_assigned; the owner (actor) did not.
    assert _unread(client, member_h) == 1
    assert _unread(client, owner_h) == 0
    n = client.get("/notifications", headers=member_h).json()[0]
    assert n["type"] == "task_assigned"
    assert n["subject_id"] == task_id

    # The member comments -> the owner (task creator) is notified; the member
    # (author) is not self-notified.
    client.post(
        "/messages",
        headers=member_h,
        json={"project_id": project_id, "task_id": task_id, "body": "started on this"},
    )
    assert _unread(client, owner_h) == 1
    assert client.get("/notifications", headers=owner_h).json()[0]["type"] == "task_commented"
    assert _unread(client, member_h) == 1  # unchanged - no self-notify


def test_mention_beats_plain_comment_notification(client, owner, owner_project):
    project_id, owner_h = owner_project
    member_h, member_id = _member(client, owner, project_id)

    client.post(
        "/messages",
        headers=owner_h,
        json={"project_id": project_id, "body": "hey @Mo", "mention_user_ids": [member_id]},
    )
    notes = client.get("/notifications", headers=member_h).json()
    assert [n["type"] for n in notes] == ["mention"]  # not also project_commented


def test_mark_read(client, owner, owner_project):
    project_id, owner_h = owner_project
    member_h, member_id = _member(client, owner, project_id)
    client.post(
        f"/tasks?project_id={project_id}",
        headers=owner_h,
        json={"title": "a", "assignee_ids": [member_id]},
    )
    client.post(
        f"/tasks?project_id={project_id}",
        headers=owner_h,
        json={"title": "b", "assignee_ids": [member_id]},
    )
    assert _unread(client, member_h) == 2

    first = client.get("/notifications", headers=member_h).json()[0]["id"]
    assert client.post(
        "/notifications/read", headers=member_h, json={"ids": [first]}
    ).status_code == 204
    assert _unread(client, member_h) == 1

    assert client.post(
        "/notifications/read", headers=member_h, json={"all": True}
    ).status_code == 204
    assert _unread(client, member_h) == 0


def test_device_registration_is_idempotent(client, owner):
    body = {"fcm_token": "tok-abc-123", "platform": "android", "app_version": "0.1.0"}
    assert client.post("/devices", headers=owner["headers"], json=body).status_code == 204
    assert client.post("/devices", headers=owner["headers"], json=body).status_code == 204
