import uuid


def _op(entity_type, entity_id, op, fields=None, base_updated_at=None):
    return {
        "client_op_id": str(uuid.uuid4()),
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "op": op,
        "base_updated_at": base_updated_at,
        "fields": fields or {},
    }


def _push(client, headers, ops):
    r = client.post("/sync/push", headers=headers, json={"ops": ops})
    assert r.status_code == 200, r.text
    return r.json()


def test_create_task_offline_then_visible_everywhere(client, owner, owner_project):
    project_id, headers = owner_project
    task_id = uuid.uuid4()
    op = _op(
        "task",
        task_id,
        "upsert",
        {"project_id": project_id, "title": "Clear culvert", "priority": "high"},
    )

    res = _push(client, headers, [op])
    result = res["results"][0]
    assert result["status"] == "applied"
    assert result["server_seq"] is not None
    assert result["row"]["id"] == str(task_id)
    assert result["row"]["title"] == "Clear culvert"
    assert res["high_seq"] >= result["server_seq"]

    # Visible via the normal list and the sync stream.
    listed = client.get(f"/tasks?project_id={project_id}", headers=headers).json()
    assert [t["id"] for t in listed] == [str(task_id)]
    changes = client.get("/sync/changes?since=0", headers=headers).json()["changes"]
    assert any(c["entity_type"] == "task" and c["entity_id"] == str(task_id) for c in changes)


def test_push_is_idempotent_per_client_op_id(client, owner, owner_project):
    project_id, headers = owner_project
    task_id = uuid.uuid4()
    op = _op("task", task_id, "upsert", {"project_id": project_id, "title": "Once"})

    first = _push(client, headers, [op])["results"][0]
    again = _push(client, headers, [op])["results"][0]  # exact same client_op_id
    assert first["status"] == "applied"
    assert again["status"] == "applied"
    assert again["row"]["id"] == str(task_id)

    # Exactly one task, one collapsed change.
    assert len(client.get(f"/tasks?project_id={project_id}", headers=headers).json()) == 1
    task_changes = [
        c
        for c in client.get("/sync/changes?since=0", headers=headers).json()["changes"]
        if c["entity_type"] == "task"
    ]
    assert len(task_changes) == 1


def test_stale_update_is_a_conflict_and_server_wins(client, owner, owner_project):
    project_id, headers = owner_project
    task_id = uuid.uuid4()
    _push(
        client,
        headers,
        [_op("task", task_id, "upsert", {"project_id": project_id, "title": "v1"})],
    )

    base = client.get(f"/tasks/{task_id}", headers=headers).json()["updated_at"]

    # Someone else moves the task on (online PATCH).
    client.patch(f"/tasks/{task_id}", headers=headers, json={"title": "server-edit"})

    # Our offline edit was based on the old version.
    res = _push(
        client,
        headers,
        [_op("task", task_id, "upsert", {"title": "stale-offline-edit"}, base_updated_at=base)],
    )
    result = res["results"][0]
    assert result["status"] == "conflict"
    assert result["row"]["title"] == "server-edit"  # server value returned, unchanged
    assert client.get(f"/tasks/{task_id}", headers=headers).json()["title"] == "server-edit"


def test_fresh_update_applies(client, owner, owner_project):
    project_id, headers = owner_project
    task_id = uuid.uuid4()
    _push(
        client,
        headers,
        [_op("task", task_id, "upsert", {"project_id": project_id, "title": "v1"})],
    )
    base = client.get(f"/tasks/{task_id}", headers=headers).json()["updated_at"]

    res = _push(
        client,
        headers,
        [_op("task", task_id, "upsert", {"status": "in_progress"}, base_updated_at=base)],
    )
    assert res["results"][0]["status"] == "applied"
    assert res["results"][0]["row"]["status"] == "in_progress"


def test_delete_via_push(client, owner, owner_project):
    project_id, headers = owner_project
    task_id = uuid.uuid4()
    _push(
        client,
        headers,
        [_op("task", task_id, "upsert", {"project_id": project_id, "title": "Doomed"})],
    )

    res = _push(client, headers, [_op("task", task_id, "delete")])
    assert res["results"][0]["status"] == "applied"
    assert res["results"][0]["row"] is None
    assert client.get(f"/tasks/{task_id}", headers=headers).status_code == 404
    delete_change = next(
        c
        for c in client.get("/sync/changes?since=0", headers=headers).json()["changes"]
        if c["entity_type"] == "task" and c["entity_id"] == str(task_id)
    )
    assert delete_change["op"] == "delete"


def test_work_log_create_via_push(client, owner, owner_project):
    project_id, headers = owner_project
    log_id = uuid.uuid4()
    res = _push(
        client,
        headers,
        [
            _op(
                "work_log",
                log_id,
                "upsert",
                {
                    "project_id": project_id,
                    "minutes": 75,
                    "worked_on": "2026-08-31",
                    "note": "raking",
                },
            )
        ],
    )
    assert res["results"][0]["status"] == "applied"
    logs = client.get(f"/work-logs?project_id={project_id}", headers=headers).json()
    assert [log["id"] for log in logs] == [str(log_id)]
    assert logs[0]["minutes"] == 75


def test_one_bad_op_is_rejected_not_the_whole_batch(client, owner, owner_project):
    project_id, headers = owner_project
    good_id, bad_id = uuid.uuid4(), uuid.uuid4()
    bogus_project = str(uuid.uuid4())

    res = _push(
        client,
        headers,
        [
            _op("task", good_id, "upsert", {"project_id": project_id, "title": "fine"}),
            _op("task", bad_id, "upsert", {"project_id": bogus_project, "title": "nope"}),
        ],
    )
    by_id = {r["entity_id"]: r for r in res["results"]}
    assert by_id[str(good_id)]["status"] == "applied"
    assert by_id[str(bad_id)]["status"] == "rejected"
    assert len(client.get(f"/tasks?project_id={project_id}", headers=headers).json()) == 1
