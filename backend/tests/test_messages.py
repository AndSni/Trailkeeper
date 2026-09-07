import uuid

from tests.conftest import auth_headers


def _member(client, owner, project_id, email="m@example.com"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "editor"}
    ).json()["token"]
    tokens = client.post(
        "/auth/invite/accept",
        json={"token": token, "name": "Mo Member", "password": "yet another phrase"},
    ).json()
    me = client.get("/auth/me", headers=auth_headers(tokens["access_token"])).json()
    uid = me["user"]["id"]
    client.post(
        f"/projects/{project_id}/members",
        headers=owner["headers"],
        json={"user_id": uid, "project_role": "member"},
    )
    return auth_headers(tokens["access_token"]), uid


def _outsider(client, owner, email="out@example.com"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "editor"}
    ).json()["token"]
    return auth_headers(
        client.post(
            "/auth/invite/accept",
            json={"token": token, "name": "Out", "password": "yet another phrase"},
        ).json()["access_token"]
    )


def test_project_thread_message_roundtrips(client, owner, owner_project):
    project_id, headers = owner_project
    r = client.post(
        "/messages", headers=headers, json={"project_id": project_id, "body": "kickoff Saturday"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["task_id"] is None

    listed = client.get(f"/messages?project_id={project_id}", headers=headers).json()
    assert [m["body"] for m in listed] == ["kickoff Saturday"]

    snap = client.get(f"/sync/snapshot?project={project_id}", headers=headers).json()
    assert [m["body"] for m in snap["messages"]] == ["kickoff Saturday"]
    changes = client.get("/sync/changes?since=0", headers=headers).json()["changes"]
    assert any(c["entity_type"] == "message" for c in changes)


def test_task_thread_is_separate_from_project_thread(client, owner, owner_project):
    project_id, headers = owner_project
    task_id = client.post(
        f"/tasks?project_id={project_id}", headers=headers, json={"title": "Bench cut"}
    ).json()["id"]

    client.post(
        "/messages", headers=headers, json={"project_id": project_id, "body": "project note"}
    )
    client.post(
        "/messages",
        headers=headers,
        json={"project_id": project_id, "task_id": task_id, "body": "task note"},
    )

    proj_thread = client.get(f"/messages?project_id={project_id}", headers=headers).json()
    task_thread = client.get(
        f"/messages?project_id={project_id}&task_id={task_id}", headers=headers
    ).json()
    assert [m["body"] for m in proj_thread] == ["project note"]
    assert [m["body"] for m in task_thread] == ["task note"]


def test_mentions_are_filtered_to_project_members(client, owner, owner_project):
    project_id, headers = owner_project
    _member_headers, member_id = _member(client, owner, project_id)
    stranger = str(uuid.uuid4())

    r = client.post(
        "/messages",
        headers=headers,
        json={
            "project_id": project_id,
            "body": "@Mo take a look",
            "mention_user_ids": [member_id, stranger],
        },
    )
    assert r.status_code == 201
    assert r.json()["mentioned_user_ids"] == [member_id]


def test_delete_is_author_or_admin_only(client, owner, owner_project):
    project_id, headers = owner_project
    member_headers, _ = _member(client, owner, project_id)

    mid = client.post(
        "/messages", headers=headers, json={"project_id": project_id, "body": "owner msg"}
    ).json()["id"]

    assert client.delete(f"/messages/{mid}", headers=member_headers).status_code == 403
    assert client.delete(f"/messages/{mid}", headers=headers).status_code == 204
    assert client.get(f"/messages?project_id={project_id}", headers=headers).json() == []


def test_outsider_cannot_read_or_post(client, owner, owner_project):
    project_id, _ = owner_project
    out = _outsider(client, owner)
    assert client.get(f"/messages?project_id={project_id}", headers=out).status_code == 404
    posted = client.post(
        "/messages", headers=out, json={"project_id": project_id, "body": "hi"}
    )
    assert posted.status_code == 404


def test_post_message_via_sync_push(client, owner, owner_project):
    project_id, headers = owner_project
    msg_id = str(uuid.uuid4())
    res = client.post(
        "/sync/push",
        headers=headers,
        json={
            "ops": [
                {
                    "client_op_id": str(uuid.uuid4()),
                    "entity_type": "message",
                    "entity_id": msg_id,
                    "op": "upsert",
                    "base_updated_at": None,
                    "fields": {"project_id": project_id, "body": "queued offline comment"},
                }
            ]
        },
    ).json()
    assert res["results"][0]["status"] == "applied"
    assert res["results"][0]["row"]["body"] == "queued offline comment"
    listed = client.get(f"/messages?project_id={project_id}", headers=headers).json()
    assert [m["id"] for m in listed] == [msg_id]
