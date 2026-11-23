"""Hardening for a server other people can reach: headers, same-origin check, production
defaults, rate limits, job caps, password cost upgrade, administrator-only actions."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from motionproof.api import auth as auth_mod
from motionproof.api.app import create_app
from motionproof.api.jobs import JobManager
from motionproof.api.security import RateLimiter, SecurityConfig
from motionproof.cli.main import app as cli_app

API = "/api/v1"
PW = "correct horse 42"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MOTIONPROOF_PRODUCTION", "MOTIONPROOF_SECURE_COOKIES", "MOTIONPROOF_REGISTRATION",
                 "MOTIONPROOF_DOCS", "MOTIONPROOF_SERIAL", "MOTIONPROOF_ALLOWED_ORIGINS",
                 "MOTIONPROOF_MAX_JOBS_PER_USER"):
        monkeypatch.delenv(name, raising=False)


def signed_in(tmp_path: Path, email: str = "a@lab.org") -> TestClient:
    c = TestClient(create_app(tmp_path))
    assert c.post(f"{API}/auth/register", json={"email": email, "password": PW}).status_code == 201
    return c


# ------------------------------------------------------------------ headers and origin


def test_security_headers_on_every_response(tmp_path: Path) -> None:
    c = TestClient(create_app(tmp_path))
    for r in (c.get(f"{API}/health"), c.get(f"{API}/projects")):        # one is a 401
        h = r.headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer"
        assert "default-src 'self'" in h["content-security-policy"]
        assert "frame-ancestors 'none'" in h["content-security-policy"]
        assert "script-src 'self'" in h["content-security-policy"]
        assert "strict-transport-security" not in h          # plain http on a developer machine
    assert c.get(f"{API}/projects").headers["cache-control"] == "private, no-cache"


def test_cross_origin_state_changes_are_refused(tmp_path: Path) -> None:
    c = signed_in(tmp_path)
    evil = {"Origin": "https://evil.example"}
    assert c.post(f"{API}/projects", json={"name": "x"}, headers=evil).status_code == 403
    assert c.post(f"{API}/auth/logout", headers=evil).status_code == 403
    assert c.get(f"{API}/projects", headers=evil).status_code == 200      # reads are not changes
    same = {"Origin": "http://testserver"}
    assert c.post(f"{API}/projects", json={"name": "ok"}, headers=same).status_code == 201
    assert c.post(f"{API}/projects", json={"name": "curl"}).status_code == 201   # no Origin header


def test_extra_origins_can_be_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_ALLOWED_ORIGINS", "https://app.example.org/")
    c = signed_in(tmp_path)
    r = c.post(f"{API}/projects", json={"name": "x"}, headers={"Origin": "https://app.example.org"})
    assert r.status_code == 201


# ------------------------------------------------------------------ production defaults


def test_production_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_mod.AuthStore(tmp_path).register("admin@lab.org", PW, "Admin")      # made on the server
    monkeypatch.setenv("MOTIONPROOF_PRODUCTION", "1")
    c = TestClient(create_app(tmp_path))
    cfg = SecurityConfig.from_env()
    assert cfg.secure_cookies and cfg.registration == "closed" and not cfg.docs and not cfg.serial
    assert c.get(f"{API}/auth/config").json() == {"registration": "closed"}
    r = c.post(f"{API}/auth/register", json={"email": "new@lab.org", "password": PW})
    assert r.status_code == 403 and "closed" in r.json()["detail"]
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
    login = c.post(f"{API}/auth/login", json={"email": "admin@lab.org", "password": PW})
    assert login.status_code == 200
    cookie = login.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "max-age=31536000" in login.headers["strict-transport-security"]


def test_defaults_stay_convenient_without_production(tmp_path: Path) -> None:
    c = TestClient(create_app(tmp_path))
    assert c.get(f"{API}/auth/config").json() == {"registration": "open"}
    assert c.get("/openapi.json").status_code == 200
    assert not SecurityConfig.from_env().hsts and not SecurityConfig.from_env().secure_cookies


def test_registration_can_be_closed_on_its_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_REGISTRATION", "closed")
    c = TestClient(create_app(tmp_path))
    assert c.post(f"{API}/auth/register", json={"email": "a@lab.org", "password": PW}).status_code == 403
    monkeypatch.setenv("MOTIONPROOF_REGISTRATION", "sometimes")
    with pytest.raises(ValueError):
        SecurityConfig.from_env()


# ------------------------------------------------------------------ administrator-only actions


def test_admin_adds_accounts_even_when_registration_is_closed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_mod.AuthStore(tmp_path).register("admin@lab.org", PW, "Admin")
    monkeypatch.setenv("MOTIONPROOF_REGISTRATION", "closed")
    admin = TestClient(create_app(tmp_path))
    assert admin.post(f"{API}/auth/login", json={"email": "admin@lab.org", "password": PW}).status_code == 200
    r = admin.post(f"{API}/admin/users", json={"email": "m@lab.org", "password": PW, "name": "M"})
    assert r.status_code == 201 and r.json()["admin"] is False
    assert admin.post(f"{API}/admin/users", json={"email": "m@lab.org", "password": PW}).status_code == 409
    member = TestClient(create_app(tmp_path))
    assert member.post(f"{API}/auth/login", json={"email": "m@lab.org", "password": PW}).status_code == 200
    assert member.post(f"{API}/admin/users", json={"email": "x@lab.org", "password": PW}).status_code == 403


def test_only_the_administrator_downloads_datasets(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    admin, member = TestClient(app), TestClient(app)
    admin.post(f"{API}/auth/register", json={"email": "a@lab.org", "password": PW})
    member.post(f"{API}/auth/register", json={"email": "b@lab.org", "password": PW})
    assert member.post(f"{API}/external/datasets/anchor_lab/import").status_code == 403
    assert admin.post(f"{API}/external/datasets/nope/import").status_code == 404   # past the check


def test_hardware_cannot_open_arbitrary_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"model_id": "MDL_001", "device": "/etc/passwd", "test": {}, "limits": {},
            "confirm_actuation": True}
    c = signed_in(tmp_path)
    r = c.post(f"{API}/hardware/experiments", json=body)
    assert r.status_code == 422 and "unknown serial device" in r.json()["detail"]
    monkeypatch.setenv("MOTIONPROOF_SERIAL", "0")
    c2 = signed_in(tmp_path / "b")
    r = c2.post(f"{API}/hardware/experiments", json=body | {"device": "COM3"})
    assert r.status_code == 403 and "disabled" in r.json()["detail"]


# ------------------------------------------------------------------ limits


def test_rate_limiter_window() -> None:
    lim = RateLimiter(2, 60)
    assert lim.hit("a") == 0 and lim.hit("a") == 0
    assert 0 < lim.hit("a") <= 60 and lim.check("a") > 0
    assert lim.hit("b") == 0 and lim.check("c") == 0


def test_repeated_failed_sign_ins_from_one_address_are_stopped(tmp_path: Path) -> None:
    c = signed_in(tmp_path)
    c.cookies.clear()
    for i in range(20):
        r = c.post(f"{API}/auth/login", json={"email": f"nobody{i}@lab.org", "password": "wrong-pass"})
        assert r.status_code == 401
    blocked = c.post(f"{API}/auth/login", json={"email": "a@lab.org", "password": PW})
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0


def test_new_accounts_per_address_are_limited_and_duplicates_are_cheap(tmp_path: Path) -> None:
    c = TestClient(create_app(tmp_path))
    for i in range(10):
        assert c.post(f"{API}/auth/register",
                      json={"email": f"u{i}@lab.org", "password": PW}).status_code == 201
    assert c.post(f"{API}/auth/register", json={"email": "u0@lab.org", "password": PW}).status_code == 409
    over = c.post(f"{API}/auth/register", json={"email": "u99@lab.org", "password": PW})
    assert over.status_code == 429


def test_jobs_per_account_are_capped() -> None:
    jobs = JobManager(workers=1, max_per_user=1)
    release = threading.Event()

    def hold(update: Any, cancel: Any) -> int:
        release.wait(30)
        return 1

    token = auth_mod.current_user.set(1)
    try:
        jobs.submit("t", "x", hold)
        with pytest.raises(HTTPException) as exc:
            jobs.submit("t", "y", hold)
        assert exc.value.status_code == 429 and "limit 1" in exc.value.detail
    finally:
        auth_mod.current_user.reset(token)
    other = auth_mod.current_user.set(2)             # another account is not affected
    try:
        jobs.submit("t", "z", hold)
    finally:
        auth_mod.current_user.reset(other)
        release.set()


# ------------------------------------------------------------------ passwords


def test_old_password_hashes_are_upgraded_at_the_next_sign_in(tmp_path: Path) -> None:
    store = auth_mod.AuthStore(tmp_path)
    store.register("old@lab.org", PW, "Old")
    salt = b"s" * 16
    with sqlite3.connect(tmp_path / "auth.db") as db:      # an account made at the old cost
        db.execute("UPDATE users SET salt = ?, hash = ?, kdf = ? WHERE email = 'old@lab.org'",
                   (salt, auth_mod._hash_password(PW, salt, auth_mod.OLD_LOG_N), auth_mod.OLD_LOG_N))
    c = TestClient(create_app(tmp_path))
    assert c.post(f"{API}/auth/login", json={"email": "old@lab.org", "password": PW}).status_code == 200
    with sqlite3.connect(tmp_path / "auth.db") as db:
        kdf, new_salt = db.execute("SELECT kdf, salt FROM users").fetchone()
    assert kdf == auth_mod.LOG_N and new_salt != salt
    c.cookies.clear()
    assert c.post(f"{API}/auth/login", json={"email": "old@lab.org", "password": PW}).status_code == 200
    c.cookies.clear()
    bad = c.post(f"{API}/auth/login", json={"email": "old@lab.org", "password": "wrong-password"})
    assert bad.status_code == 401


def test_schema_without_the_kdf_column_is_migrated(tmp_path: Path) -> None:
    store = auth_mod.AuthStore(tmp_path)
    store.register("a@lab.org", PW, "A")
    with sqlite3.connect(tmp_path / "auth.db") as db:
        db.execute("ALTER TABLE users DROP COLUMN kdf")
    auth_mod.AuthStore(tmp_path)                            # opening it adds the column back
    with sqlite3.connect(tmp_path / "auth.db") as db:
        assert db.execute("SELECT kdf FROM users").fetchone()[0] == auth_mod.OLD_LOG_N


# ------------------------------------------------------------------ account commands


def test_account_commands_create_list_and_reset(tmp_path: Path) -> None:
    runner = CliRunner()
    home = ["--home", str(tmp_path)]
    r = runner.invoke(cli_app, ["account", "create", "boss@lab.org", *home], input=f"{PW}\n{PW}\n")
    assert r.exit_code == 0 and "administrator" in r.output
    r = runner.invoke(cli_app, ["account", "create", "short@lab.org", *home], input="abc\nabc\n")
    assert r.exit_code != 0                                  # too short
    scripted = runner.invoke(cli_app, ["account", "create", "bot@lab.org", "--password-stdin", *home],
                             input=f"{PW}\n")
    assert scripted.exit_code == 0 and "bot@lab.org" in scripted.output
    assert "boss@lab.org" in runner.invoke(cli_app, ["account", "list", *home]).output
    new = "another long password 9"
    r = runner.invoke(cli_app, ["account", "reset-password", "boss@lab.org", *home],
                      input=f"{new}\n{new}\n")
    assert r.exit_code == 0
    c = TestClient(create_app(tmp_path))
    assert c.post(f"{API}/auth/login", json={"email": "boss@lab.org", "password": PW}).status_code == 401
    assert c.post(f"{API}/auth/login", json={"email": "boss@lab.org", "password": new}).status_code == 200
    r = runner.invoke(cli_app, ["account", "reset-password", "ghost@lab.org", *home], input="x\nx\n")
    assert r.exit_code != 0
