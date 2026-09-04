"""Test fixtures.

Tests run against a real Postgres database (Trailkeeper has spatial ambitions
from Phase 1, so SQLite is not a useful stand-in even now). Point them at one
with TEST_DATABASE_URL, or let it default to the local `trailkeeper_test`
database beside the dev one. Each test runs inside a transaction that is
rolled back at the end, so the schema is created once and never mutated.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

_DEFAULT = "postgresql+psycopg://sharpright:sharpright_dev@127.0.0.1:5432/trailkeeper_test"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", _DEFAULT)

# Make the app pick up the test URL before anything imports app.db / app.config.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-" + "0" * 24)
os.environ.setdefault("ALLOW_REGISTRATION", "true")


@pytest.fixture(scope="session")
def _engine():
    try:
        engine = create_engine(TEST_DATABASE_URL, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"No test database reachable at {TEST_DATABASE_URL}: {exc}")

    from app import models  # noqa: F401
    from app.db import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db(_engine) -> Session:
    connection = _engine.connect()
    trans = connection.begin()
    session = sessionmaker(bind=connection, future=True)()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def owner(client):
    """Register an owner + their organisation; return auth context."""
    resp = client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "name": "Olive Owner",
            "password": "correct horse battery",
            "organisation_name": "Gauja Trail Crew",
        },
    )
    assert resp.status_code == 201, resp.text
    tokens = resp.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    org_id = client.get("/auth/me", headers=headers).json()["memberships"][0]["organisation_id"]
    return {"headers": headers, "tokens": tokens, "org_id": org_id}


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
