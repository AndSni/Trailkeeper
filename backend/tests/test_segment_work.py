from tests.conftest import auth_headers

# ~1 km line at 57N (0.009 deg latitude) and a short one for a second record.
LINE_1KM = {"type": "LineString", "coordinates": [[24.0, 57.0], [24.0, 57.009]]}
LINE_HALF = {"type": "LineString", "coordinates": [[24.1, 57.0], [24.1, 57.0045]]}


def _job(client, headers, key):
    return next(j for j in client.get("/job-types", headers=headers).json() if j["key"] == key)


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


def _create(client, headers, project_id, job_type_id, **over):
    body = {
        "project_id": project_id,
        "job_type_id": job_type_id,
        "geometry": LINE_1KM,
        "quantity_source": "measured",
        "started_at": "2026-08-30T08:00:00Z",
        "ended_at": "2026-08-30T08:40:00Z",
        "active_seconds": 2400,
        "crew_size": 2,
        "equipment": ["brushcutter"],
    }
    body.update(over)
    return client.post("/segment-work", headers=headers, json=body)


def test_measured_quantity_and_derived_numbers(client, owner, owner_project):
    project_id, headers = owner_project
    bc = _job(client, headers, "brushcutting")  # unit km, expected_rate 22 min/km

    r = _create(client, headers, project_id, bc["id"])
    assert r.status_code == 201, r.text
    rec = r.json()

    assert rec["unit"] == "km"
    assert abs(rec["quantity"] - 1.0) < 0.02  # ST_Length geography of the ~1km line
    # 2400 s active, 2-person crew -> 2400/3600*2 = 1.333 person-hours
    assert rec["person_hours"] == 1.333
    # rate = (2400/60) / quantity ~= 40 min/km
    assert abs(rec["rate_min_per_unit"] - 40.0 / rec["quantity"]) < 0.01
    assert abs(rec["vs_expected_min_per_unit"] - (rec["rate_min_per_unit"] - 22.0)) < 0.01
    assert rec["geometry"]["type"] == "LineString"


def test_manual_count_record(client, owner, owner_project):
    project_id, headers = owner_project
    dip = _job(client, headers, "drainage_dip")  # unit count

    r = _create(
        client,
        headers,
        project_id,
        dip["id"],
        geometry=None,
        quantity_source="manual",
        quantity=8,
        crew_size=1,
        active_seconds=3000,
    )
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["unit"] == "count"
    assert rec["quantity"] == 8.0
    assert rec["geometry"] is None
    # rate = (3000/60) / 8 = 6.25 min each ; expected 6.0 -> delta +0.25
    assert abs(rec["rate_min_per_unit"] - 6.25) < 0.01
    assert abs(rec["vs_expected_min_per_unit"] - 0.25) < 0.01


def test_syncs_and_author_only_edit(client, owner, owner_project):
    project_id, headers = owner_project
    bc = _job(client, headers, "brushcutting")
    member_h, _ = _member(client, owner, project_id)

    rec_id = _create(client, headers, project_id, bc["id"]).json()["id"]

    # in snapshot + changes
    snap = client.get(f"/sync/snapshot?project={project_id}", headers=headers).json()
    assert [s["id"] for s in snap["segment_work"]] == [rec_id]
    changes = client.get("/sync/changes?since=0", headers=headers).json()["changes"]
    assert any(c["entity_type"] == "segment_work" and c["entity_id"] == rec_id for c in changes)

    # a non-author member can't edit or delete
    assert client.patch(
        f"/segment-work/{rec_id}", headers=member_h, json={"crew_size": 5}
    ).status_code == 403
    assert client.delete(f"/segment-work/{rec_id}", headers=member_h).status_code == 403

    # the author can - and person_hours recomputes
    up = client.patch(f"/segment-work/{rec_id}", headers=headers, json={"crew_size": 1})
    assert up.status_code == 200
    assert up.json()["person_hours"] == round(2400 / 3600 * 1, 3)

    assert client.delete(f"/segment-work/{rec_id}", headers=headers).status_code == 204
    del_change = next(
        c
        for c in client.get("/sync/changes?since=0", headers=headers).json()["changes"]
        if c["entity_type"] == "segment_work" and c["entity_id"] == rec_id
    )
    assert del_change["op"] == "delete"


def test_rollup_by_job_type(client, owner, owner_project):
    project_id, headers = owner_project
    bc = _job(client, headers, "brushcutting")

    a = _create(
        client, headers, project_id, bc["id"],
        geometry=LINE_1KM, active_seconds=2400, crew_size=2,
    ).json()
    b = _create(
        client, headers, project_id, bc["id"],
        geometry=LINE_HALF, active_seconds=1500, crew_size=1,
    ).json()
    total_qty = a["quantity"] + b["quantity"]

    rollup = client.get(
        f"/segment-work/rollup?project_id={project_id}&group_by=job_type", headers=headers
    ).json()
    assert rollup["group_by"] == "job_type"
    g = next(x for x in rollup["groups"] if x["group_label"] == "Brushcutting")
    assert g["record_count"] == 2
    assert g["unit"] == "km"
    assert abs(g["total_quantity"] - total_qty) < 0.01
    assert abs(g["total_person_hours"] - (2400 / 3600 * 2 + 1500 / 3600 * 1)) < 0.01
    # weighted mean rate = total minutes / total quantity
    assert abs(g["mean_rate_min_per_unit"] - ((2400 + 1500) / 60) / total_qty) < 0.02
    assert g["expected_rate"] == 22.0
    assert g["delta_min_per_unit"] is not None


def test_rollup_by_member_and_week(client, owner, owner_project):
    project_id, headers = owner_project
    bc = _job(client, headers, "brushcutting")
    _create(client, headers, project_id, bc["id"])

    for dim in ("member", "week"):
        rollup = client.get(
            f"/segment-work/rollup?project_id={project_id}&group_by={dim}", headers=headers
        ).json()
        assert rollup["group_by"] == dim
        assert len(rollup["groups"]) == 1
        assert rollup["groups"][0]["record_count"] == 1

    assert (
        client.get(
            f"/segment-work/rollup?project_id={project_id}&group_by=bogus", headers=headers
        ).status_code
        == 400
    )
