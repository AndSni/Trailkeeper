"""Web console (server-rendered) - auth pages + dashboard."""


def _register(client, email="console@example.com"):
    return client.post(
        "/register",
        data={
            "organisation_name": "Console Crew",
            "name": "Cass",
            "email": email,
            "password": "a decent long passphrase",
        },
        follow_redirects=False,
    )


def test_index_and_login_page(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"

    page = client.get("/login")
    assert page.status_code == 200
    assert "Sign in" in page.text


def test_app_requires_session(client):
    r = client.get("/app", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert r.headers["location"] == "/login"


def test_register_sets_session_and_dashboard_loads(client):
    r = _register(client)
    assert r.status_code == 303
    assert r.headers["location"] == "/app"
    assert "tk_session" in r.cookies

    dash = client.get("/app")  # client keeps the cookie
    assert dash.status_code == 200
    assert "Console Crew" in dash.text
    assert "Structures by status" in dash.text


def test_dashboard_shows_project_sections(client):
    _register(client, email="p@example.com")
    # the console's session cookie also authenticates the JSON API? no - use the
    # API with its own token. Grab one via the JSON login.
    tokens = client.post(
        "/auth/login",
        json={"email": "p@example.com", "password": "a decent long passphrase"},
    ).json()
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.post("/projects", headers=h, json={"name": "Blue Trail", "activity": "mtb"})

    dash = client.get("/app")
    assert dash.status_code == 200
    assert "Blue Trail" in dash.text
    assert "Job-type productivity" in dash.text
    assert "Hours per member" in dash.text


def test_login_bad_credentials_rerenders(client):
    _register(client, email="real@example.com")
    client.get("/logout")
    r = client.post(
        "/login",
        data={"email": "real@example.com", "password": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "Invalid email or password" in r.text


def test_members_page_and_invite_creation(client):
    _register(client, email="admin@example.com")

    members = client.get("/app/members")
    assert members.status_code == 200
    assert "admin@example.com" in members.text

    made = client.post(
        "/app/invites",
        data={"email": "newbie@example.com", "org_role": "editor"},
        follow_redirects=False,
    )
    assert made.status_code == 303
    assert "/app/members?invited=" in made.headers["location"]
    token = made.headers["location"].split("invited=")[1]

    invite_page = client.get(f"/invite/{token}")
    assert invite_page.status_code == 200
    assert "Join Console Crew" in invite_page.text

    accepted = client.post(
        f"/invite/{token}",
        data={"name": "Newbie", "password": "another good passphrase"},
        follow_redirects=False,
    )
    assert accepted.status_code == 303
    assert accepted.headers["location"] == "/app"
    assert "tk_session" in accepted.cookies


def test_invite_page_invalid_token(client):
    page = client.get("/invite/not-a-real-token")
    assert page.status_code == 200
    assert "Invite not valid" in page.text
