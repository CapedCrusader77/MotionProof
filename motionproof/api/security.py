"""Security settings and middleware for the MotionProof server.

``MOTIONPROOF_PRODUCTION=1`` (or ``motionproof serve --production``) switches on the settings for a
server other people can reach: Secure cookies, closed registration, no interactive API docs, HSTS,
no serial devices and a smaller job queue per account. Each setting can still be changed with its
own variable. Without it everything stays as convenient as before for a single user on localhost.

  MOTIONPROOF_PRODUCTION          1 for a hosted server
  MOTIONPROOF_SECURE_COOKIES      1 forces the Secure flag (default: on in production; otherwise
                                  only when the request itself arrived over https)
  MOTIONPROOF_REGISTRATION        open | closed (production default: closed; accounts are then made
                                  by the administrator, or with `motionproof account create`)
  MOTIONPROOF_DOCS                1/0, the /docs page and /openapi.json (production default: off)
  MOTIONPROOF_SERIAL              1/0, hardware tests on serial ports of the server
                                  (production default: off)
  MOTIONPROOF_ALLOWED_ORIGINS     comma-separated extra origins allowed to send state-changing
                                  requests (default: the site itself)
  MOTIONPROOF_MAX_JOBS_PER_USER   queued plus running jobs per account (default 8; production 4)
  MOTIONPROOF_TRUSTED_PROXIES     addresses whose X-Forwarded-* headers are believed
                                  (`serve --production` default: 127.0.0.1)
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

TRUE = ("1", "true", "yes", "on")
UNSAFE = ("POST", "PUT", "PATCH", "DELETE")

# The web app loads nothing from other origins, so the policy can be strict. Inline styles are
# used by the React components (style attributes), hence 'unsafe-inline' for styles only.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
       "worker-src 'self' blob:; media-src 'self' blob:; object-src 'none'; base-uri 'self'; "
       "form-action 'self'; frame-ancestors 'none'")


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in TRUE


@dataclass(frozen=True)
class SecurityConfig:
    production: bool = False
    secure_cookies: bool = False
    registration: str = "open"
    docs: bool = True
    serial: bool = True
    hsts: bool = False
    allowed_origins: tuple[str, ...] = ()
    max_jobs_per_user: int = 8

    @classmethod
    def from_env(cls) -> SecurityConfig:
        prod = _flag("MOTIONPROOF_PRODUCTION", False)
        registration = os.environ.get("MOTIONPROOF_REGISTRATION", "").strip().lower() \
            or ("closed" if prod else "open")
        if registration not in ("open", "closed"):
            raise ValueError("MOTIONPROOF_REGISTRATION must be open or closed")
        origins = tuple(o.strip().rstrip("/").lower()
                        for o in os.environ.get("MOTIONPROOF_ALLOWED_ORIGINS", "").split(",")
                        if o.strip())
        try:
            jobs = int(os.environ.get("MOTIONPROOF_MAX_JOBS_PER_USER", "") or (4 if prod else 8))
        except ValueError:
            jobs = 4 if prod else 8
        return cls(production=prod, secure_cookies=_flag("MOTIONPROOF_SECURE_COOKIES", prod),
                   registration=registration, docs=_flag("MOTIONPROOF_DOCS", not prod),
                   serial=_flag("MOTIONPROOF_SERIAL", not prod), hsts=prod,
                   allowed_origins=origins, max_jobs_per_user=max(1, jobs))


class RateLimiter:
    """At most ``limit`` events per ``window`` seconds for each key (kept in memory)."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> float:
        """0 if another event is allowed now, else seconds until it would be (records nothing)."""
        now = time.monotonic()
        with self._lock:
            q = self._events.get(key)
            if q is None:
                return 0.0
            while q and now - q[0] > self.window:
                q.popleft()
            return self.window - (now - q[0]) if len(q) >= self.limit else 0.0

    def hit(self, key: str) -> float:
        """Record an event. Returns 0 if allowed, else the seconds until it would be."""
        now = time.monotonic()
        with self._lock:
            q = self._events.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return self.window - (now - q[0])
            q.append(now)
            if len(self._events) > 10_000:       # forget idle keys
                for k in [k for k, v in self._events.items() if not v or now - v[-1] > self.window]:
                    del self._events[k]
        return 0.0


def _origin_ok(request: Request, cfg: SecurityConfig) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        return True        # not a browser cross-site request (SameSite=Strict stops those)
    origin = origin.rstrip("/").lower()
    if origin in cfg.allowed_origins:
        return True
    host = request.headers.get("host", "").lower()
    return urlparse(origin).netloc == host


def install(app: FastAPI, cfg: SecurityConfig, api: str) -> None:
    """Security headers on every response and a same-origin check on state-changing API calls."""
    app.state.security = cfg

    @app.middleware("http")
    async def guard(request: Request,
                    call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if request.method in UNSAFE and path.startswith(api + "/") and not _origin_ok(request, cfg):
            response: Response = JSONResponse(
                status_code=403, content={"error": "cross-origin request refused"})
        else:
            response = await call_next(request)
        h = response.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), usb=(), serial=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        if path not in ("/docs", "/redoc"):      # the API docs pages load their own scripts
            h["Content-Security-Policy"] = CSP
        if cfg.hsts:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if path.startswith(api + "/") and "cache-control" not in h:
            h["Cache-Control"] = "private, no-cache"   # data belongs to the signed-in account
        return response
