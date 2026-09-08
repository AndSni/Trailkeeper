from tests.conftest import auth_headers

CULVERT_FIELDS = [
    {"key": "blocked", "label": "Inlet blocked?", "type": "bool"},
    {
        "key": "scour",
        "label": "Scour severity",
        "type": "choice",
        "choices": ["none", "minor", "major"],
    },
    {"key": "note", "label": "Notes", "type": "text"},
]


def _editor(client, owner, email="ed@example.com"):
    token = client.post(
        "/org/invites", headers=owner["headers"], json={"email": email, "org_role": "editor"}
    ).json()["token"]
    return auth_headers(
        client.post(
            "/auth/invite/accept",
            json={"token": token, "name": "Ed", "password": "yet another phrase"},
        ).json()["access_token"]
    )


def test_create_validates_fields(client, owner):
    r = client.post(
        "/inspection-forms",
        headers=owner["headers"],
        json={"name": "Culvert check", "target_type": "culvert", "fields": CULVERT_FIELDS},
    )
    assert r.status_code == 201, r.text
    form = r.json()
    assert form["version"] == 1
    assert len(form["fields"]) == 3

    bad_type = client.post(
        "/inspection-forms",
        headers=owner["headers"],
        json={"name": "x", "fields": [{"key": "a", "type": "rating"}]},
    )
    assert bad_type.status_code == 400

    dup = client.post(
        "/inspection-forms",
        headers=owner["headers"],
        json={"name": "x", "fields": [{"key": "a", "type": "bool"}, {"key": "a", "type": "text"}]},
    )
    assert dup.status_code == 400

    choiceless = client.post(
        "/inspection-forms",
        headers=owner["headers"],
        json={"name": "x", "fields": [{"key": "a", "type": "choice"}]},
    )
    assert choiceless.status_code == 400


def test_patch_bumps_version(client, owner):
    fid = client.post(
        "/inspection-forms",
        headers=owner["headers"],
        json={"name": "Bridge check", "fields": [{"key": "deck", "type": "bool"}]},
    ).json()["id"]

    up = client.patch(
        f"/inspection-forms/{fid}",
        headers=owner["headers"],
        json={"fields": [{"key": "deck", "type": "bool"}, {"key": "rails", "type": "bool"}]},
    )
    assert up.status_code == 200
    assert up.json()["version"] == 2
    assert len(up.json()["fields"]) == 2


def test_editor_cannot_mutate(client, owner):
    editor = _editor(client, owner)
    assert (
        client.post(
            "/inspection-forms", headers=editor, json={"name": "x", "fields": []}
        ).status_code
        == 403
    )
    assert client.get("/inspection-forms", headers=editor).status_code == 200


def test_syncs_and_delete(client, owner, owner_project):
    project_id, headers = owner_project
    fid = client.post(
        "/inspection-forms",
        headers=headers,
        json={"name": "Sign check", "fields": [{"key": "legible", "type": "bool"}]},
    ).json()["id"]

    snap = client.get(f"/sync/snapshot?project={project_id}", headers=headers).json()
    assert fid in {f["id"] for f in snap["inspection_forms"]}

    assert client.delete(f"/inspection-forms/{fid}", headers=headers).status_code == 204
    snap2 = client.get(f"/sync/snapshot?project={project_id}", headers=headers).json()
    assert fid not in {f["id"] for f in snap2["inspection_forms"]}
