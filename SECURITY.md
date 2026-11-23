# Security

MotionProof is a local engineering tool for one person or a small trusted group. On your own
computer, run it bound to `127.0.0.1` (the default). To let others reach it, follow
[`docs/hosting.md`](docs/hosting.md): run `motionproof serve --production` behind an https
reverse proxy, or keep it on a private network.

* **Accounts.** Every `/api/v1` route except `GET /health`, `GET /auth/config` and the sign-in
  routes needs a session. Passwords are stored as scrypt hashes (64 MB, about 0.35 s, a random
  salt per account; older accounts are upgraded at their next sign-in); only a SHA-256 of each
  session token is stored. The token travels in an HttpOnly, SameSite=Strict cookie, marked Secure
  in production or whenever the request arrived over https. Sessions last 14 days; signing out
  deletes the session on the server.
* **Production mode** (`--production`): Secure cookies, closed registration (accounts are made
  by the administrator or with `motionproof account create`), HSTS, no `/docs` or
  `/openapi.json`, no hardware tests on the server's serial ports, 4 jobs queued or running per
  account.
* **Browser protections.** A strict Content-Security-Policy (the app loads nothing from other
  origins), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, and a
  same-origin check on every state-changing API request (on top of SameSite=Strict cookies).
* **Isolation.** Each account has its own workspace (the first account keeps the workspace root,
  later accounts get `users/<id>/`) and sees only its own jobs. Members are not shown the
  server's folder paths, and only the administrator can download datasets.
* **Limits.** Five failed sign-ins for one email lock it for 60 s (stored in `auth.db`, survives a
  restart); 20 failed sign-ins per address in 10 minutes and 10 new accounts per address per hour
  are refused (kept in memory); a duplicate email is refused before any password hashing.
* **Administration.** The first account is the administrator: it can list accounts, add an
  account, set a new password for another account (which signs that account out everywhere) and
  delete one. Every account can change its own password (other sessions are signed out) and
  delete itself after entering its password. The last administrator cannot be deleted.
* **Logs.** Sign-ins, failed sign-ins (with the address), account creation, password changes and
  deletions are logged by the `motionproof.auth` logger. Passwords and tokens are never logged.
* **Public health check.** `GET /health` answers only `{"status": "ok"}`; versions, paths and job
  counts are at `GET /system`, behind sign-in.
* **Dependencies.** CI fails on a known vulnerability in the locked Python or JavaScript
  dependencies, and Dependabot proposes updates.
* Uploads are limited to 300 MB (CAD) and 50 MB (measurements), stored under sanitised names,
  and never executed. No CAD macros or scripts are run.
* Paths inside a model directory are resolved and refused if they leave it.
* No shell commands are built from user input.
* Project deletion requires the project id as explicit confirmation.
* The optional AI assistant receives only a digest of one experiment's stored results. By default
  it talks to a local Ollama server. With `MOTIONPROOF_AI_PROVIDER=anthropic` or `openai` it sends
  that digest and the question to the provider over https; the API key comes from the server's
  environment only (never stored, never sent to the browser, never in a response or error), each
  account has a daily question limit, and the interface says where the data goes. Disable it with
  `MOTIONPROOF_AI=off`. See [`docs/ai-assistant.md`](docs/ai-assistant.md).
* MotionProof does not connect to actuators or other hardware except through the hardware
  module, which needs an explicit confirmation before it moves anything.

Not provided: multi-factor sign-in, self-service password reset by email, email verification, or more than one
administrator. A deleted account's workspace folder stays on disk.

Report problems to the project owner privately before publishing details.
