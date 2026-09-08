from tests.conftest import auth_headers


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


def _structure(client, headers, name="Culvert A", stype="culvert"):
    return client.post(
        "/structures", headers=headers, json={"name": name, "structure_type": stype}
    ).json()["id"]


def _form(client, headers):
    return client.post(
        "/inspection-forms",
        headers=headers,
        json={"name": "Culvert check", "fields": [{"key": "blocked", "type": "bool"}]},
    ).json()


def test_create_pins_form_version_and_applies_condition(client, owner, owner_project):
    project_id, headers = owner_project
    sid = _structure(client, headers)
    form = _form(client, headers)
    # bump the form so the pinned version is not just 1
    client.patch(
        f"/inspection-forms/{form['id']}",
        headers=headers,
        json={"fields": [{"key": "blocked", "type": "bool"}, {"key": "scour", "type": "bool"}]},
    )

    r = client.post(
        "/inspections",
        headers=headers,
        json={
            "project_id": project_id,
            "structure_id": sid,
            "form_id": form["id"],
            "answers": {"blocked": True, "scour": False},
            "risk": "high",
            "condition": "needs_repair",
            "notes": "inlet silted",
        },
    )
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["form_version"] == 2
    assert rec["risk"] == "high"

    # condition wrote back to the structure
    s = client.get(f"/structures/{sid}", headers=headers).json()
    assert s["status"] == "needs_repair"


def test_list_filter_and_author_only_edit(client, owner, owner_project):
    project_id, headers = owner_project
    sid_a = _structure(client, headers, "A")
    sid_b = _structure(client, headers, "B")
    member_h, _ = _member(client, owner, project_id)

    rec_id = client.post(
        "/inspections",
        headers=headers,
        json={"project_id": project_id, "structure_id": sid_a, "risk": "low"},
    ).json()["id"]
    client.post(
        "/inspections",
        headers=headers,
        json={"project_id": project_id, "structure_id": sid_b},
    )

    all_recs = client.get(f"/inspections?project_id={project_id}", headers=headers).json()
    assert len(all_recs) == 2
    just_a = client.get(
        f"/inspections?project_id={project_id}&structure_id={sid_a}", headers=headers
    ).json()
    assert [x["id"] for x in just_a] == [rec_id]

    # a non-author member can't edit or delete
    assert client.patch(
        f"/inspections/{rec_id}", headers=member_h, json={"risk": "critical"}
    ).status_code == 403
    assert client.delete(f"/inspections/{rec_id}", headers=member_h).status_code == 403

    # the author can
    up = client.patch(f"/inspections/{rec_id}", headers=headers, json={"risk": "medium"})
    assert up.status_code == 200
    assert up.json()["risk"] == "medium"


def test_unknown_structure_rejected(client, owner, owner_project):
    project_id, headers = owner_project
    import uuid

    r = client.post(
        "/inspections",
        headers=headers,
        json={"project_id": project_id, "structure_id": str(uuid.uuid4())},
    )
    assert r.status_code == 400


def test_syncs_project_scoped(client, owner, owner_project):
    project_id, headers = owner_project
    sid = _structure(client, headers)
    rec_id = client.post(
        "/inspections",
        headers=headers,
        json={"project_id": project_id, "structure_id": sid, "risk": "low"},
    ).json()["id"]

    snap = client.get(f"/sync/snapshot?project={project_id}", headers=headers).json()
    assert [i["id"] for i in snap["inspections"]] == [rec_id]

    changes = client.get("/sync/changes?since=0", headers=headers).json()["changes"]
    change = next(
        c for c in changes if c["entity_type"] == "inspection" and c["entity_id"] == rec_id
    )
    assert change["project_id"] == project_id

    assert client.delete(f"/inspections/{rec_id}", headers=headers).status_code == 204
    del_change = next(
        c
        for c in client.get("/sync/changes?since=0", headers=headers).json()["changes"]
        if c["entity_type"] == "inspection" and c["entity_id"] == rec_id
    )
    assert del_change["op"] == "delete"
