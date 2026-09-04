from tests.conftest import auth_headers


def test_register_returns_tokens_and_makes_owner(client):
    resp = client.post(
        "/auth/register",
        json={
            "email": "a@example.com",
            "name": "Aina",
            "password": "a strong passphrase",
            "organisation_name": "Crew",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]

    me = client.get("/auth/me", headers=auth_headers(body["access_token"]))
    assert me.status_code == 200
    data = me.json()
    assert data["user"]["email"] == "a@example.com"
    assert data["memberships"][0]["org_role"] == "owner"


def test_duplicate_email_conflicts(client):
    payload = {
        "email": "dup@example.com",
        "name": "Dup",
        "password": "one two three four",
        "organisation_name": "Crew",
    }
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_login_ok_and_bad_password(client, owner):
    ok = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery"},
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = client.post(
        "/auth/login", json={"email": "owner@example.com", "password": "wrong"}
    )
    assert bad.status_code == 401


def test_refresh_rotates_access(client, owner):
    refreshed = client.post(
        "/auth/refresh", json={"refresh_token": owner["tokens"]["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    # An access token is not a refresh token.
    assert (
        client.post(
            "/auth/refresh", json={"refresh_token": owner["tokens"]["access_token"]}
        ).status_code
        == 401
    )


def test_me_requires_auth(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
