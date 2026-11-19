"""Accounts and sessions: the API refuses work without a session and checks passwords."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from motionproof.api import auth as auth_mod
from motionproof.api.app import create_app

EMAIL, PASSWORD = "Engineer@Lab.org", "correct horse 42"


@pytest.fixture()
def client(tmp_path) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(create_app(tmp_path))


def test_api_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/v1/health").status_code == 200
    r = client.get("/api/v1/projects")
    assert r.status_code == 401
    assert r.json() == {"error": "sign in to continue"}
    assert client.get("/api/v1/auth/me").status_code == 401


def test_register_sign_out_sign_in(client: TestClient) -> None:
    r = client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD,
                                                   "name": "Ada"})
    assert r.status_code == 201
    assert r.json()["user"] == {"id": 1, "email": "engineer@lab.org", "name": "Ada"}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/v1/projects").status_code == 200
    assert client.get("/api/v1/auth/me").json()["user"]["email"] == "engineer@lab.org"

    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/projects").status_code == 401

    # email is case-insensitive
    r = client.post("/api/v1/auth/login", json={"email": "ENGINEER@lab.org",
                                                "password": PASSWORD})
    assert r.status_code == 200
    assert client.get("/api/v1/projects").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    client.cookies.clear()
    wrong = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "nope-nope"})
    unknown = client.post("/api/v1/auth/login", json={"email": "x@y.org", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert client.get("/api/v1/projects").status_code == 401


def test_registration_rules(client: TestClient) -> None:
    assert client.post("/api/v1/auth/register",
                       json={"email": "not-an-email", "password": PASSWORD}).status_code == 422
    assert client.post("/api/v1/auth/register",
                       json={"email": EMAIL, "password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/register",
                       json={"email": EMAIL, "password": PASSWORD}).status_code == 201
    assert client.post("/api/v1/auth/register",
                       json={"email": EMAIL.lower(), "password": PASSWORD}).status_code == 409


def test_repeated_failures_are_throttled(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    client.cookies.clear()
    for _ in range(auth_mod.MAX_FAILURES):
        assert client.post("/api/v1/auth/login",
                           json={"email": EMAIL, "password": "wrong-pass"}).status_code == 401
    # locked even with the right password until the lock expires
    assert client.post("/api/v1/auth/login",
                       json={"email": EMAIL, "password": PASSWORD}).status_code == 429


def test_passwords_and_tokens_are_not_stored_in_clear(client: TestClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    token = r.cookies.get(auth_mod.COOKIE) or client.cookies.get(auth_mod.COOKIE)
    assert token
    raw = (tmp_path / "auth.db").read_bytes()
    assert PASSWORD.encode() not in raw and token.encode() not in raw
    with sqlite3.connect(tmp_path / "auth.db") as c:
        (stored,) = c.execute("SELECT token_hash FROM sessions").fetchone()
    assert stored == auth_mod._token_hash(token)


def test_forged_cookie_is_refused(client: TestClient) -> None:
    client.cookies.set(auth_mod.COOKIE, "forged-token")
    assert client.get("/api/v1/projects").status_code == 401


def test_public_health_reveals_nothing(client: TestClient) -> None:
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/system").status_code == 401
    client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    detail = client.get("/api/v1/system").json()
    assert {"versions", "workspace", "active_jobs", "ai"} <= detail.keys()


def test_each_account_has_its_own_workspace(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(tmp_path)
    a, b = TestClient(app), TestClient(app)
    a.post("/api/v1/auth/register", json={"email": "a@lab.org", "password": PASSWORD})
    b.post("/api/v1/auth/register", json={"email": "b@lab.org", "password": PASSWORD})
    pid = a.post("/api/v1/projects", json={"name": "A's bracket"}).json()["id"]

    assert [p["name"] for p in a.get("/api/v1/projects").json()] == ["A's bracket"]
    assert b.get("/api/v1/projects").json() == []
    assert b.get(f"/api/v1/projects/{pid}").status_code == 404
    # the first account keeps the workspace root; later accounts get their own folder
    assert a.get("/api/v1/system").json()["workspace"] == str(tmp_path.resolve())
    assert b.get("/api/v1/system").json()["workspace"] == str((tmp_path / "users" / "2").resolve())


def test_jobs_are_private_to_their_owner(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(tmp_path)
    a, b = TestClient(app), TestClient(app)
    a.post("/api/v1/auth/register", json={"email": "a@lab.org", "password": PASSWORD})
    b.post("/api/v1/auth/register", json={"email": "b@lab.org", "password": PASSWORD})
    from motionproof.api.auth import current_user

    token = current_user.set(1)
    try:
        job = app.state.jobs.submit("test", "x", lambda update, cancel: 42)
    finally:
        current_user.reset(token)
    assert a.get(f"/api/v1/jobs/{job['id']}").status_code == 200
    assert b.get(f"/api/v1/jobs/{job['id']}").status_code == 404
    assert b.post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 404
