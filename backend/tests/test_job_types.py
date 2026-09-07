from tests.conftest import auth_headers


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


def test_defaults_seeded_on_register(client, owner):
    jts = client.get("/job-types", headers=owner["headers"]).json()
    keys = {j["key"] for j in jts}
    assert {"brushcutting", "drainage_dip", "general"} <= keys
    bc = next(j for j in jts if j["key"] == "brushcutting")
    assert bc["unit"] == "km"
    assert bc["expected_rate"] == 22.0


def test_create_patch_delete(client, owner, owner_project):
    project_id, headers = owner_project

    created = client.post(
        "/job-types",
        headers=headers,
        json={"key": "rock_armour", "label": "Rock armouring", "unit": "m2", "expected_rate": 90},
    )
    assert created.status_code == 201, created.text
    jt_id = created.json()["id"]

    # duplicate key -> 409
    assert (
        client.post(
            "/job-types",
            headers=headers,
            json={"key": "rock_armour", "label": "dup", "unit": "m2"},
        ).status_code
        == 409
    )
    # bad unit -> 400
    assert (
        client.post(
            "/job-types", headers=headers, json={"key": "x", "label": "x", "unit": "furlongs"}
        ).status_code
        == 400
    )

    patched = client.patch(f"/job-types/{jt_id}", headers=headers, json={"expected_rate": 75})
    assert patched.status_code == 200
    assert patched.json()["expected_rate"] == 75.0

    assert client.delete(f"/job-types/{jt_id}", headers=headers).status_code == 204
    assert jt_id not in {j["id"] for j in client.get("/job-types", headers=headers).json()}

    snap = client.get(f"/sync/snapshot?project={project_id}", headers=headers).json()
    assert jt_id not in {j["id"] for j in snap["job_types"]}
    assert len(snap["job_types"]) >= 8


def test_editor_cannot_mutate(client, owner):
    editor = _editor(client, owner)
    assert (
        client.post(
            "/job-types", headers=editor, json={"key": "x", "label": "x", "unit": "count"}
        ).status_code
        == 403
    )
    # ...but can read
    assert client.get("/job-types", headers=editor).status_code == 200
