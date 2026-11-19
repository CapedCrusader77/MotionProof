"""Accounts and sessions for the MotionProof API.

Passwords are stored as scrypt hashes (``hashlib.scrypt``, per-user random salt). Signing in
creates a random session token; only its SHA-256 is stored, and the token travels in an
HttpOnly, SameSite=Strict cookie, so plain links (report downloads, artifact files) work and
page scripts cannot read it. Every ``/api/v1`` route except health, sign-in and registration
answers 401 without a valid session.

Each account has its own workspace: the request's user is held in a context variable and
``UserStores`` hands every route the ``Store`` of that user. The first account keeps the
workspace root (where any data from before accounts existed lives); later accounts get
``<home>/users/<id>``.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from motionproof.persistence.store import Store

COOKIE = "mp_session"
SESSION_SECONDS = 14 * 24 * 3600
MIN_PASSWORD = 8
# sign-in throttling: after this many failures for one email, wait LOCK_SECONDS
MAX_FAILURES = 5
LOCK_SECONDS = 60
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  salt BLOB NOT NULL,
  hash BLOB NOT NULL,
  created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires REAL NOT NULL
);
"""

# Paths under /api/v1 that work without a session.
PUBLIC = {"/health", "/auth/login", "/auth/register", "/auth/me", "/auth/logout"}
# /health answers only {"status": "ok"}; server details are at /system, behind sign-in.


# id of the signed-in user for the current request (and the jobs it starts)
current_user: contextvars.ContextVar[int | None] = contextvars.ContextVar("mp_user", default=None)


class UserStores:
    """Stands in for a ``Store``: every attribute is looked up on the current user's store."""

    def __init__(self, home: Path):
        object.__setattr__(self, "_root", home)
        object.__setattr__(self, "_stores", {})
        object.__setattr__(self, "_lock", threading.Lock())

    def for_user(self, user_id: int) -> Store:
        stores: dict[int, Store] = object.__getattribute__(self, "_stores")
        with object.__getattribute__(self, "_lock"):
            if user_id not in stores:
                root: Path = object.__getattribute__(self, "_root")
                stores[user_id] = Store(root if user_id == 1 else root / "users" / str(user_id))
            return stores[user_id]

    def __getattr__(self, name: str) -> Any:
        uid = current_user.get()
        if uid is None:
            raise RuntimeError("no signed-in user for this workspace access")
        return getattr(self.for_user(uid), name)


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class Registration(Credentials):
    name: str = Field(default="", max_length=120)


class AuthStore:
    """Users and sessions in ``<home>/auth.db`` (SQLite)."""

    def __init__(self, home: Path):
        self.path = home / "auth.db"
        self._lock = threading.Lock()
        self._failures: dict[str, tuple[int, float]] = {}
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.execute("PRAGMA foreign_keys = ON")
        return c

    @staticmethod
    def _user(row: tuple[Any, ...]) -> dict[str, Any]:
        return {"id": row[0], "email": row[1], "name": row[2]}

    def register(self, email: str, password: str, name: str) -> dict[str, Any]:
        email = email.strip().lower()
        if not _EMAIL.match(email):
            raise ValueError("enter a valid email address, like name@lab.org")
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"the password needs at least {MIN_PASSWORD} characters")
        salt = secrets.token_bytes(16)
        digest = _hash_password(password, salt)
        with self._lock, closing(self._conn()) as c, c:
            try:
                cur = c.execute("INSERT INTO users (email, name, salt, hash, created) "
                                "VALUES (?, ?, ?, ?, ?)",
                                (email, name.strip() or email.split("@")[0], salt, digest,
                                 time.time()))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "an account with this email already exists") from None
            row = c.execute("SELECT id, email, name FROM users WHERE id = ?",
                            (cur.lastrowid,)).fetchone()
        return self._user(row)

    def authenticate(self, email: str, password: str) -> dict[str, Any]:
        email = email.strip().lower()
        count, until = self._failures.get(email, (0, 0.0))
        if count >= MAX_FAILURES and time.time() < until:
            raise HTTPException(429, "too many failed sign-ins; try again in a minute")
        with closing(self._conn()) as c:
            row = c.execute("SELECT id, email, name, salt, hash FROM users WHERE email = ?",
                            (email,)).fetchone()
        # hash even for an unknown email, so the response time does not reveal which exist
        salt, stored = (row[3], row[4]) if row else (b"\0" * 16, b"")
        ok = hmac.compare_digest(_hash_password(password, salt), stored) and row is not None
        if not ok:
            count = count + 1 if time.time() < until or count < MAX_FAILURES else 1
            self._failures[email] = (count, time.time() + LOCK_SECONDS)
            raise HTTPException(401, "the email or password is not correct")
        self._failures.pop(email, None)
        return self._user(row)

    def open_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock, closing(self._conn()) as c, c:
            c.execute("DELETE FROM sessions WHERE expires < ?", (now,))
            c.execute("INSERT INTO sessions (token_hash, user_id, expires) VALUES (?, ?, ?)",
                      (_token_hash(token), user_id, now + SESSION_SECONDS))
        return token

    def session_user(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with closing(self._conn()) as c:
            row = c.execute("SELECT u.id, u.email, u.name FROM sessions s JOIN users u "
                            "ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires > ?",
                            (_token_hash(token), time.time())).fetchone()
        return self._user(row) if row else None

    def close_session(self, token: str | None) -> None:
        if token:
            with self._lock, closing(self._conn()) as c, c:
                c.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def install(app: FastAPI, home: Path, api: str) -> AuthStore:
    """Add the auth routes and the middleware that guards the rest of the API."""
    auth = AuthStore(home)
    app.state.auth = auth

    def set_cookie(response: Response, request: Request, token: str) -> None:
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                            samesite="strict", secure=request.url.scheme == "https", path="/")

    @app.middleware("http")
    async def require_session(request: Request,
                              call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if (path.startswith(api + "/") and request.method != "OPTIONS"
                and path[len(api):] not in PUBLIC):
            user = auth.session_user(request.cookies.get(COOKIE))
            if user is None:
                return JSONResponse(status_code=401, content={"error": "sign in to continue"})
            request.state.user = user
            reset = current_user.set(user["id"])
            try:
                return await call_next(request)
            finally:
                current_user.reset(reset)
        return await call_next(request)

    @app.post(f"{api}/auth/register", status_code=201)
    def register(body: Registration, request: Request, response: Response) -> dict[str, Any]:
        user = auth.register(body.email, body.password, body.name)
        set_cookie(response, request, auth.open_session(user["id"]))
        return {"user": user}

    @app.post(f"{api}/auth/login")
    def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
        user = auth.authenticate(body.email, body.password)
        set_cookie(response, request, auth.open_session(user["id"]))
        return {"user": user}

    @app.post(f"{api}/auth/logout")
    def logout(request: Request, response: Response) -> dict[str, Any]:
        auth.close_session(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get(f"{api}/auth/me")
    def me(request: Request) -> dict[str, Any]:
        user = auth.session_user(request.cookies.get(COOKIE))
        if user is None:
            raise HTTPException(401, "not signed in")
        return {"user": user}

    return auth
