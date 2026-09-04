from tests.conftest import auth_headers


def _invite_editor(client, owner, email="ed@example.com"):
    token = client.post(
        "/org/invites",
        headers=owner["headers"],
        json={"email": email, "org_role": "editor"},
    ).json()["token"]
    accepted = client.post(
        "/auth/invite/accept",
        json={"token": token, "name": "Ed Editor", "password": "yet another phrase"},
    ).json()
    me = client.get("/auth/me", headers=auth_headers(accepted["access_token"])).json()
    return auth_headers(accepted["access_token"]), me["user"]["id"]


def test_owner_creates_and_lists_project(client, owner):
    resp = client.post(
        "/projects",
        headers=owner["headers"],
        json={"name": "Blue Trail Rebuild", "activity": "mtb"},
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]
    assert resp.json()["status"] == "planning"

    listed = client.get("/projects", headers=owner["headers"]).json()
    assert [p["id"] for p in listed] == [pid]


def test_editor_sees_only_projects_they_belong_to(client, owner):
    pid = client.post(
        "/projects", headers=owner["headers"], json={"name": "Hidden"}
    ).json()["id"]
    editor_headers, editor_uid = _invite_editor(client, owner)

    assert client.get("/projects", headers=editor_headers).json() == []
    assert client.get(f"/projects/{pid}", headers=editor_headers).status_code == 404

    add = client.post(
        f"/projects/{pid}/members",
        headers=owner["headers"],
        json={"user_id": editor_uid, "project_role": "member"},
    )
    assert add.status_code == 201

    listed = client.get("/projects", headers=editor_headers).json()
    assert [p["id"] for p in listed] == [pid]
    assert client.get(f"/projects/{pid}", headers=editor_headers).status_code == 200


def test_editor_cannot_create_project(client, owner):
    editor_headers, _ = _invite_editor(client, owner)
    resp = client.post("/projects", headers=editor_headers, json={"name": "Nope"})
    assert resp.status_code == 403


def test_project_lead_can_edit_but_plain_member_cannot(client, owner):
    pid = client.post(
        "/projects", headers=owner["headers"], json={"name": "Grade Reversal Day"}
    ).json()["id"]
    editor_headers, editor_uid = _invite_editor(client, owner)
    client.post(
        f"/projects/{pid}/members",
        headers=owner["headers"],
        json={"user_id": editor_uid, "project_role": "member"},
    )

    assert (
        client.patch(
            f"/projects/{pid}", headers=editor_headers, json={"status": "active"}
        ).status_code
        == 403
    )

    client.post(
        f"/projects/{pid}/members",
        headers=owner["headers"],
        json={"user_id": editor_uid, "project_role": "lead"},
    )
    ok = client.patch(
        f"/projects/{pid}", headers=editor_headers, json={"status": "active"}
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "active"


def test_soft_delete_hides_project(client, owner):
    pid = client.post(
        "/projects", headers=owner["headers"], json={"name": "Doomed"}
    ).json()["id"]
    assert client.delete(f"/projects/{pid}", headers=owner["headers"]).status_code == 204
    assert client.get("/projects", headers=owner["headers"]).json() == []
    assert client.get(f"/projects/{pid}", headers=owner["headers"]).status_code == 404


def test_status_filter(client, owner):
    a = client.post("/projects", headers=owner["headers"], json={"name": "A"}).json()["id"]
    client.post("/projects", headers=owner["headers"], json={"name": "B"})
    client.patch(f"/projects/{a}", headers=owner["headers"], json={"status": "active"})

    active = client.get("/projects?status=active", headers=owner["headers"]).json()
    assert [p["id"] for p in active] == [a]
