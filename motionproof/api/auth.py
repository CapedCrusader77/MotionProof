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

The first account is the administrator: it can list accounts, set a new password for one and
delete one. Every account can change its own password (which signs out its other sessions) and
delete itself. Failed sign-ins are counted in the database, so the throttle survives a restart.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import logging
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

from motionproof.api.security import RateLimiter, SecurityConfig
from motionproof.persistence.store import Store

COOKIE = "mp_session"
SESSION_SECONDS = 14 * 24 * 3600
MIN_PASSWORD = 8
# sign-in throttling: after this many failures for one email, wait LOCK_SECONDS
MAX_FAILURES = 5
LOCK_SECONDS = 60
# scrypt cost: N = 2**LOG_N (64 MB, about 0.35 s). Accounts made with a lower cost are rehashed at
# their next successful sign-in.
LOG_N = 16
OLD_LOG_N = 14                    # what accounts created before the cost was raised use
LOG = logging.getLogger("motionproof.auth")
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
CREATE TABLE IF NOT EXISTS failures (
  email TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  until REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_usage (
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  count INTEGER NOT NULL,
  PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires REAL NOT NULL
);
"""

# Paths under /api/v1 that work without a session.
PUBLIC = {"/health", "/auth/config", "/auth/login", "/auth/register", "/auth/me", "/auth/logout"}
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


def _hash_password(password: str, salt: bytes, log_n: int = LOG_N) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** log_n, r=8, p=1,
                          maxmem=2 ** 28, dklen=32)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class Registration(Credentials):
    name: str = Field(default="", max_length=120)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current: str = Field(min_length=1, max_length=1024)
    new: str = Field(min_length=1, max_length=1024)


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new: str = Field(min_length=1, max_length=1024)


class Rename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class Confirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=1024)


class AuthStore:
    """Users and sessions in ``<home>/auth.db`` (SQLite)."""

    def __init__(self, home: Path):
        self.path = home / "auth.db"
        self._lock = threading.Lock()
        with closing(self._conn()) as c, c:
            c.executescript(SCHEMA)
            cols = [r[1] for r in c.execute("PRAGMA table_info(users)")]
            if "kdf" not in cols:       # accounts created before the scrypt cost was raised
                c.execute(f"ALTER TABLE users ADD COLUMN kdf INTEGER NOT NULL DEFAULT {OLD_LOG_N}")
            if "is_admin" not in cols:  # accounts created before the admin role existed
                c.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
                c.execute("UPDATE users SET is_admin = 1 WHERE id = (SELECT MIN(id) FROM users)")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.execute("PRAGMA foreign_keys = ON")
        return c

    USER_COLS = "id, email, name, is_admin"

    @staticmethod
    def _user(row: tuple[Any, ...]) -> dict[str, Any]:
        return {"id": row[0], "email": row[1], "name": row[2], "admin": bool(row[3])}

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"the password needs at least {MIN_PASSWORD} characters")

    def exists(self, email: str) -> bool:
        with closing(self._conn()) as c:
            return c.execute("SELECT 1 FROM users WHERE email = ?",
                             (email.strip().lower(),)).fetchone() is not None

    def register(self, email: str, password: str, name: str) -> dict[str, Any]:
        email = email.strip().lower()
        if not _EMAIL.match(email):
            raise ValueError("enter a valid email address, like name@lab.org")
        self._check_password(password)
        salt = secrets.token_bytes(16)
        digest = _hash_password(password, salt)
        with self._lock, closing(self._conn()) as c, c:
            first = c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            try:
                cur = c.execute("INSERT INTO users (email, name, salt, hash, created, is_admin, "
                                "kdf) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (email, name.strip() or email.split("@")[0], salt, digest,
                                 time.time(), int(first), LOG_N))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "an account with this email already exists") from None
            row = c.execute(f"SELECT {self.USER_COLS} FROM users WHERE id = ?",
                            (cur.lastrowid,)).fetchone()
        return self._user(row)

    def _verify(self, user_id: int, password: str) -> None:
        with closing(self._conn()) as c:
            row = c.execute("SELECT salt, hash, kdf FROM users WHERE id = ?",
                            (user_id,)).fetchone()
        if row is None or not hmac.compare_digest(_hash_password(password, row[0], row[2]), row[1]):
            raise HTTPException(403, "the password is not correct")

    def set_password(self, user_id: int, new: str, keep_token: str | None = None) -> None:
        """Store a new password and end every session of the account except ``keep_token``."""
        self._check_password(new)
        salt = secrets.token_bytes(16)
        with self._lock, closing(self._conn()) as c, c:
            if c.execute("UPDATE users SET salt = ?, hash = ?, kdf = ? WHERE id = ?",
                         (salt, _hash_password(new, salt), LOG_N, user_id)).rowcount == 0:
                raise HTTPException(404, "no such account")
            keep = _token_hash(keep_token) if keep_token else ""
            c.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                      (user_id, keep))

    def rename(self, user_id: int, name: str) -> None:
        if not name.strip():
            raise ValueError("enter a name")
        with self._lock, closing(self._conn()) as c, c:
            c.execute("UPDATE users SET name = ? WHERE id = ?", (name.strip(), user_id))

    def sessions(self, user_id: int) -> int:
        with closing(self._conn()) as c:
            return int(c.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ? AND expires > ?",
                                 (user_id, time.time())).fetchone()[0])

    def end_other_sessions(self, user_id: int, keep_token: str | None) -> int:
        keep = _token_hash(keep_token) if keep_token else ""
        with self._lock, closing(self._conn()) as c, c:
            return c.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                             (user_id, keep)).rowcount

    @staticmethod
    def _today() -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def ai_used(self, user_id: int) -> int:
        """Cloud AI questions this account has asked today (UTC)."""
        with closing(self._conn()) as c:
            row = c.execute("SELECT count FROM ai_usage WHERE user_id = ? AND day = ?",
                            (user_id, self._today())).fetchone()
        return int(row[0]) if row else 0

    def ai_use(self, user_id: int, limit: int) -> int:
        """Count one cloud AI question, or refuse (429) once the day's limit is reached. Returns
        the questions left today. Counted before the request is sent, so a loop cannot run up a
        bill."""
        day = self._today()
        with self._lock, closing(self._conn()) as c, c:
            row = c.execute("SELECT count FROM ai_usage WHERE user_id = ? AND day = ?",
                            (user_id, day)).fetchone()
            used = int(row[0]) if row else 0
            if used >= limit:
                raise HTTPException(429, f"the daily limit of {limit} cloud AI questions is "
                                         "reached; it resets at 00:00 UTC")
            c.execute("INSERT OR REPLACE INTO ai_usage (user_id, day, count) VALUES (?, ?, ?)",
                      (user_id, day, used + 1))
            c.execute("DELETE FROM ai_usage WHERE day < ?", (day,))
        return limit - used - 1

    def users(self) -> list[dict[str, Any]]:
        with closing(self._conn()) as c:
            rows = c.execute(f"SELECT {self.USER_COLS}, created FROM users ORDER BY id").fetchall()
        return [self._user(r) | {"created": r[4]} for r in rows]

    def delete(self, user_id: int) -> None:
        """Delete an account and its sessions. The last administrator cannot be deleted. The
        account's workspace folder is left on disk."""
        with self._lock, closing(self._conn()) as c, c:
            row = c.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "no such account")
            admins = c.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]
            if row[0] and admins <= 1:
                raise HTTPException(409, "the last administrator account cannot be deleted")
            c.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def authenticate(self, email: str, password: str) -> dict[str, Any]:
        email = email.strip().lower()
        now = time.time()
        with closing(self._conn()) as c:
            f = c.execute("SELECT count, until FROM failures WHERE email = ?", (email,)).fetchone()
            row = c.execute(f"SELECT {self.USER_COLS}, salt, hash, kdf FROM users WHERE email = ?",
                            (email,)).fetchone()
        count, until = f if f else (0, 0.0)
        if count >= MAX_FAILURES and now < until:
            raise HTTPException(429, "too many failed sign-ins; try again in a minute")
        # hash even for an unknown email, so the response time does not reveal which exist
        salt, stored, log_n = (row[4], row[5], row[6]) if row else (b"\0" * 16, b"", LOG_N)
        ok = hmac.compare_digest(_hash_password(password, salt, log_n), stored) and row is not None
        with self._lock, closing(self._conn()) as c, c:
            if ok and log_n < LOG_N:      # first sign-in since the cost was raised: rehash now
                new_salt = secrets.token_bytes(16)
                c.execute("UPDATE users SET salt = ?, hash = ?, kdf = ? WHERE id = ?",
                          (new_salt, _hash_password(password, new_salt), LOG_N, row[0]))
            if not ok:
                count = count + 1 if now < until or count < MAX_FAILURES else 1
                c.execute("INSERT OR REPLACE INTO failures (email, count, until) VALUES (?, ?, ?)",
                          (email, count, now + LOCK_SECONDS))
            else:
                c.execute("DELETE FROM failures WHERE email = ?", (email,))
        if not ok:
            raise HTTPException(401, "the email or password is not correct")
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
            row = c.execute("SELECT u.id, u.email, u.name, u.is_admin FROM sessions s JOIN users u "
                            "ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires > ?",
                            (_token_hash(token), time.time())).fetchone()
        return self._user(row) if row else None

    def close_session(self, token: str | None) -> None:
        if token:
            with self._lock, closing(self._conn()) as c, c:
                c.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def install(app: FastAPI, home: Path, api: str, cfg: SecurityConfig) -> AuthStore:
    """Add the auth routes and the middleware that guards the rest of the API."""
    auth = AuthStore(home)
    app.state.auth = auth
    # failed sign-ins per address, and new accounts per address (each costs CPU and memory)
    failed_signins = RateLimiter(20, 600)
    new_accounts = RateLimiter(10, 3600)

    def set_cookie(response: Response, request: Request, token: str) -> None:
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                            samesite="strict", path="/",
                            secure=cfg.secure_cookies or request.url.scheme == "https")

    def too_many(wait: float) -> HTTPException:
        return HTTPException(429, f"too many attempts from this address; try again in "
                                  f"{int(wait) + 1} s", headers={"Retry-After": str(int(wait) + 1)})

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

    @app.get(f"{api}/auth/config")
    def auth_config() -> dict[str, Any]:
        return {"registration": cfg.registration}

    @app.post(f"{api}/auth/register", status_code=201)
    def register(body: Registration, request: Request, response: Response) -> dict[str, Any]:
        if cfg.registration == "closed":
            raise HTTPException(403, "registration is closed; ask the administrator for an account")
        if auth.exists(body.email):                  # no password hashing for a known email
            raise HTTPException(409, "an account with this email already exists")
        wait = new_accounts.hit(_ip(request))
        if wait:
            raise too_many(wait)
        user = auth.register(body.email, body.password, body.name)
        LOG.info("account created id=%s ip=%s", user["id"], _ip(request))
        set_cookie(response, request, auth.open_session(user["id"]))
        return {"user": user}

    @app.post(f"{api}/auth/login")
    def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
        wait = failed_signins.check(_ip(request))
        if wait:
            raise too_many(wait)
        try:
            user = auth.authenticate(body.email, body.password)
        except HTTPException as exc:
            if exc.status_code == 401:
                failed_signins.hit(_ip(request))
                LOG.warning("sign-in failed email=%s ip=%s", body.email.strip().lower()[:80],
                            _ip(request))
            raise
        LOG.info("sign-in id=%s ip=%s", user["id"], _ip(request))
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

    def admin(request: Request) -> dict[str, Any]:
        user: dict[str, Any] = request.state.user
        if not user["admin"]:
            raise HTTPException(403, "only the administrator can do this")
        return user

    @app.post(f"{api}/account/password")
    def change_password(body: PasswordChange, request: Request) -> dict[str, Any]:
        uid = request.state.user["id"]
        auth._verify(uid, body.current)
        auth.set_password(uid, body.new, keep_token=request.cookies.get(COOKIE))
        LOG.info("password changed id=%s ip=%s", uid, _ip(request))
        return {"ok": True}

    @app.get(f"{api}/account")
    def account(request: Request) -> dict[str, Any]:
        user = dict(request.state.user)
        return user | {"sessions": auth.sessions(user["id"])}

    @app.post(f"{api}/account/name")
    def rename(body: Rename, request: Request) -> dict[str, Any]:
        auth.rename(request.state.user["id"], body.name)
        return {"ok": True}

    @app.post(f"{api}/account/sessions/end-others")
    def end_others(request: Request) -> dict[str, Any]:
        n = auth.end_other_sessions(request.state.user["id"], request.cookies.get(COOKIE))
        return {"ended": n}

    @app.post(f"{api}/account/delete")
    def delete_self(body: Confirm, request: Request, response: Response) -> dict[str, Any]:
        uid = request.state.user["id"]
        auth._verify(uid, body.password)
        auth.delete(uid)
        LOG.info("account deleted by owner id=%s ip=%s", uid, _ip(request))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.post(f"{api}/admin/users", status_code=201)
    def create_user(body: Registration, request: Request) -> dict[str, Any]:
        me_ = admin(request)
        if auth.exists(body.email):
            raise HTTPException(409, "an account with this email already exists")
        user = auth.register(body.email, body.password, body.name)
        LOG.info("account created by admin id=%s new=%s", me_["id"], user["id"])
        return user

    @app.get(f"{api}/admin/users")
    def list_users(request: Request) -> list[dict[str, Any]]:
        admin(request)
        return auth.users()

    @app.post(f"{api}/admin/users/{{user_id}}/password")
    def reset_password(user_id: int, body: PasswordReset, request: Request) -> dict[str, Any]:
        me_ = admin(request)
        if user_id == me_["id"]:
            raise HTTPException(409, "change your own password under Account")
        auth.set_password(user_id, body.new)
        return {"ok": True}

    @app.delete(f"{api}/admin/users/{{user_id}}")
    def delete_user(user_id: int, request: Request) -> dict[str, Any]:
        me_ = admin(request)
        if user_id == me_["id"]:
            raise HTTPException(409, "delete your own account under Account")
        auth.delete(user_id)
        return {"ok": True}

    return auth
