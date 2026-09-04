from datetime import UTC

from tests.conftest import auth_headers


def _accept_invite(client, token, name="Ivo Invitee", password="another good phrase"):
    return client.post(
        "/auth/invite/accept",
        json={"token": token, "name": name, "password": password},
    )


def test_invite_flow_creates_member(client, owner):
    inv = client.post(
        "/org/invites",
        headers=owner["headers"],
        json={"email": "ivo@example.com", "org_role": "editor"},
    )
    assert inv.status_code == 201
    token = inv.json()["token"]

    accepted = _accept_invite(client, token)
    assert accepted.status_code == 201
    new_headers = auth_headers(accepted.json()["access_token"])

    me = client.get("/auth/me", headers=new_headers).json()
    assert me["user"]["email"] == "ivo@example.com"
    assert me["memberships"][0]["org_role"] == "editor"
    assert me["memberships"][0]["organisation_id"] == owner["org_id"]

    members = client.get("/org/members", headers=owner["headers"]).json()
    assert {m["email"] for m in members} == {"owner@example.com", "ivo@example.com"}


def test_editor_cannot_invite(client, owner):
    token = client.post(
        "/org/invites",
        headers=owner["headers"],
        json={"email": "ivo@example.com", "org_role": "editor"},
    ).json()["token"]
    editor_headers = auth_headers(_accept_invite(client, token).json()["access_token"])

    resp = client.post(
        "/org/invites",
        headers=editor_headers,
        json={"email": "x@example.com", "org_role": "viewer"},
    )
    assert resp.status_code == 403


def test_expired_invite_rejected(client, owner, db):
    from datetime import datetime, timedelta

    from app.models import Invite

    token = client.post(
        "/org/invites",
        headers=owner["headers"],
        json={"email": "late@example.com", "org_role": "viewer"},
    ).json()["token"]

    invite = db.query(Invite).filter(Invite.token == token).one()
    invite.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()

    assert _accept_invite(client, token).status_code == 410


def test_cannot_demote_last_owner(client, owner):
    me = client.get("/auth/me", headers=owner["headers"]).json()
    owner_user_id = me["user"]["id"]
    resp = client.patch(
        f"/org/members/{owner_user_id}",
        headers=owner["headers"],
        json={"org_role": "admin"},
    )
    assert resp.status_code == 409


def test_admin_can_update_org(client, owner):
    resp = client.patch("/org", headers=owner["headers"], json={"name": "Renamed Crew"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed Crew"
