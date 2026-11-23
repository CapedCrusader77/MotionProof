# Security

MotionProof is a local engineering tool. Run it bound to `127.0.0.1` (the default); to share it
on a network, put it behind HTTPS.

* **Accounts.** Every `/api/v1` route except `GET /health` and the sign-in routes needs a
  session. Passwords are stored as scrypt hashes with a random salt per account (`auth.db` in
  the workspace); only a SHA-256 of each session token is stored. The token travels in an
  HttpOnly, SameSite=Strict cookie, marked Secure when the server is reached over HTTPS.
  Sessions last 14 days; signing out deletes the session on the server.
* **Isolation.** Each account has its own workspace (the first account keeps the workspace root,
  later accounts get `users/<id>/`) and sees only its own jobs.
* **Throttling.** Five failed sign-ins for one email lock it for 60 s. The counter is stored in
  `auth.db`, so a restart does not reset it.
* **Administration.** The first account is the administrator: it can list accounts, set a new
  password for another account (which signs that account out everywhere) and delete one. Every
  account can change its own password (other sessions are signed out) and delete itself after
  entering its password. The last administrator cannot be deleted.
* **Public health check.** `GET /health` answers only `{"status": "ok"}`; versions, paths and job
  counts are at `GET /system`, behind sign-in.

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

Not provided: self-service password reset by email, email verification, or more than one
administrator. A deleted account's workspace folder stays on disk.

Report problems to the project owner privately before publishing details.
