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
    assert r.json()["user"] == {"id": 1, "email": "engineer@lab.org", "name": "Ada",
                                "admin": True}
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


def _two(tmp_path):  # type: ignore[no-untyped-def]
    app = create_app(tmp_path)
    a, b = TestClient(app), TestClient(app)
    a.post("/api/v1/auth/register", json={"email": "a@lab.org", "password": PASSWORD})
    b.post("/api/v1/auth/register", json={"email": "b@lab.org", "password": PASSWORD})
    return app, a, b


def test_first_account_is_the_only_admin(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, a, b = _two(tmp_path)
    assert a.get("/api/v1/auth/me").json()["user"]["admin"] is True
    assert b.get("/api/v1/auth/me").json()["user"]["admin"] is False
    assert [u["email"] for u in a.get("/api/v1/admin/users").json()] == ["a@lab.org", "b@lab.org"]
    assert b.get("/api/v1/admin/users").status_code == 403


def test_change_password_signs_out_other_sessions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app, a, _ = _two(tmp_path)
    other = TestClient(app)
    other.post("/api/v1/auth/login", json={"email": "a@lab.org", "password": PASSWORD})
    assert other.get("/api/v1/projects").status_code == 200
    bad = a.post("/api/v1/account/password", json={"current": "wrong-one", "new": "new-pass-123"})
    assert bad.status_code == 403
    assert a.post("/api/v1/account/password",
                  json={"current": PASSWORD, "new": "short"}).status_code == 422
    assert a.post("/api/v1/account/password",
                  json={"current": PASSWORD, "new": "new-pass-123"}).status_code == 200
    assert a.get("/api/v1/projects").status_code == 200          # this session stays
    assert other.get("/api/v1/projects").status_code == 401      # the other one ends
    fresh = TestClient(app)
    assert fresh.post("/api/v1/auth/login",
                      json={"email": "a@lab.org", "password": PASSWORD}).status_code == 401
    assert fresh.post("/api/v1/auth/login",
                      json={"email": "a@lab.org", "password": "new-pass-123"}).status_code == 200


def test_admin_resets_a_password_and_deletes_an_account(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app, a, b = _two(tmp_path)
    assert b.post("/api/v1/admin/users/1/password", json={"new": "taken-over-1"}).status_code == 403
    assert a.post("/api/v1/admin/users/2/password", json={"new": "reset-pass-1"}).status_code == 200
    assert b.get("/api/v1/projects").status_code == 401           # b's sessions ended
    c = TestClient(app)
    assert c.post("/api/v1/auth/login",
                  json={"email": "b@lab.org", "password": "reset-pass-1"}).status_code == 200
    assert a.delete("/api/v1/admin/users/1").status_code == 409   # not yourself here
    assert a.delete("/api/v1/admin/users/2").status_code == 200
    assert c.get("/api/v1/projects").status_code == 401
    assert a.delete("/api/v1/admin/users/2").status_code == 404


def test_delete_own_account_needs_the_password(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, a, b = _two(tmp_path)
    assert b.post("/api/v1/account/delete", json={"password": "wrong-one"}).status_code == 403
    assert b.post("/api/v1/account/delete", json={"password": PASSWORD}).status_code == 200
    assert b.get("/api/v1/projects").status_code == 401
    # the last administrator cannot remove itself
    assert a.post("/api/v1/account/delete", json={"password": PASSWORD}).status_code == 409


def test_throttle_survives_a_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c = TestClient(create_app(tmp_path))
    c.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    for _ in range(auth_mod.MAX_FAILURES):
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "wrong-pass"})
    restarted = TestClient(create_app(tmp_path))
    assert restarted.post("/api/v1/auth/login",
                          json={"email": EMAIL, "password": PASSWORD}).status_code == 429


def test_accounts_from_before_the_admin_role_get_one(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c = TestClient(create_app(tmp_path))
    c.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    with sqlite3.connect(tmp_path / "auth.db") as db:   # simulate the old schema
        db.execute("ALTER TABLE users DROP COLUMN is_admin")
    c2 = TestClient(create_app(tmp_path))
    c2.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert c2.get("/api/v1/auth/me").json()["user"]["admin"] is True


def test_rename_and_sign_out_other_sessions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app, a, _ = _two(tmp_path)
    other = TestClient(app)
    other.post("/api/v1/auth/login", json={"email": "a@lab.org", "password": PASSWORD})
    assert a.get("/api/v1/account").json()["sessions"] == 2
    assert a.post("/api/v1/account/name", json={"name": "  Gokul  "}).status_code == 200
    assert a.get("/api/v1/auth/me").json()["user"]["name"] == "Gokul"
    assert a.post("/api/v1/account/name", json={"name": ""}).status_code == 422
    assert a.post("/api/v1/account/sessions/end-others").json() == {"ended": 1}
    assert other.get("/api/v1/projects").status_code == 401
    assert a.get("/api/v1/account").json()["sessions"] == 1
