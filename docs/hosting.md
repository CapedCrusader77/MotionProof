# Hosting MotionProof

MotionProof is one Python process (the API, the simulations and the built web app) with its data in
a folder. It is built for one person or a small trusted group. This page says where to run it and
how to run it safely.

## Recommendation

| Who needs access | Do this | Why |
|---|---|---|
| Only you, or a lab or team you know | **Run it on one machine and reach it over [Tailscale](https://tailscale.com)** (a private network); no public port | Nothing is exposed to the internet, no certificate to manage, and each person signs in to the tailnet first, then to MotionProof |
| People outside a private network | **A small Linux server (VPS) with the Caddy web server in front**, as below | Caddy gets and renews the https certificate by itself; MotionProof only listens on the server itself |
| Just you, on your own computer | `uv run motionproof serve` and open `http://127.0.0.1:8000` | Nothing leaves the machine, and there is no sign-in. Do not use `--host 0.0.0.0` without the steps below |

**Not suitable:** Vercel, Netlify, GitHub Pages and other serverless or static hosts (the backend
runs long simulations and keeps files), and free container tiers with 512 MB of memory or an
ephemeral disk (the workspace would be lost and CadQuery and MuJoCo need more memory).

**Size (an estimate, not measured on every host):** 2 CPU cores and 4 GB of memory to start; 4
cores and 8 GB if several people run large experiments. A reference scenario takes about 0.5 s of
one core (measured on a laptop), so 1000 scenarios take about 9 minutes on one core, or about half
that with 4 workers.

## What the server does for you

Start it with `--production` (or set `MOTIONPROOF_PRODUCTION=1`) and these turn on:

* Cookies are marked `Secure`; the server answers with HSTS, a strict Content-Security-Policy and
  the usual protective headers. Requests that change data must come from the site itself.
* **Registration is closed.** Nobody can create an account over the web. The first account is made
  on the server with `motionproof account create`; the administrator then adds the others under
  Settings, Administration.
* The interactive API pages (`/docs`, `/openapi.json`) and hardware tests on the server's serial
  ports are off. Only the administrator can download datasets.
* Passwords are stored as scrypt hashes (64 MB, about 0.35 s per check), failed sign-ins are
  throttled per account and per address, and each account may have 4 jobs queued or running.

Everything above can be set one by one; the variables are listed at the top of
`motionproof/api/security.py`.

## A public server, step by step

These steps follow what the project's CI does on Ubuntu 24.04 (`uv sync`, frontend build, tests).
The service and Caddy files in `deploy/` are standard, but they have not been run on a live server
by the project: read them before using them.

1. **Server.** A fresh Ubuntu LTS VPS. Point a DNS record (for example `motionproof.example.com`)
   at it. Log in with an SSH key and turn off password logins.
2. **Firewall.** Allow only SSH, http and https:
   ```bash
   sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
   ```
3. **Tools, user and code.** Install [uv](https://docs.astral.sh/uv/) for all users
   (`curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh`) and
   Node 24 (for example from NodeSource). Then:
   ```bash
   sudo useradd --system --create-home --home-dir /var/lib/motionproof --shell /usr/sbin/nologin motionproof
   sudo git clone https://github.com/CapedCrusader77/MotionProof /opt/motionproof
   sudo chown -R motionproof:motionproof /opt/motionproof
   ```
4. **Install and build**, as that user, so the Python it downloads is readable by the service:
   ```bash
   cd /opt/motionproof
   sudo -u motionproof -H uv sync --locked
   cd frontend && sudo -u motionproof -H npm ci && sudo -u motionproof -H npm run build
   ```
5. **First account** (this account is the administrator):
   ```bash
   sudo -u motionproof /opt/motionproof/.venv/bin/motionproof account create you@example.com \
     --home /var/lib/motionproof/workspace
   ```
6. **Service.** Copy `deploy/motionproof.service` to `/etc/systemd/system/`, then
   `sudo systemctl enable --now motionproof`. Optional settings and secrets go in
   `/etc/motionproof.env` (see `deploy/motionproof.env.example`; `chmod 600`).
7. **https.** Install [Caddy](https://caddyserver.com/docs/install), put `deploy/Caddyfile` in
   `/etc/caddy/Caddyfile` with your host name, and `sudo systemctl reload caddy`.
8. **Check it** from your own computer:
   ```bash
   curl -sI https://motionproof.example.com/ | grep -iE "strict-transport|content-security|x-frame"
   curl -s https://motionproof.example.com/api/v1/auth/config      # {"registration":"closed"}
   ```
   and try `http://motionproof.example.com`, which should redirect to https.

The application listens on `127.0.0.1` only, so the only way in is through Caddy. If you put
another proxy in front, give its address with `--trusted-proxies` so sign-in limits see the real
client address.

## Private access with Tailscale

Install Tailscale on the machine that runs MotionProof and on each person's device, then:

```bash
uv run motionproof serve --production --home workspace      # listens on 127.0.0.1 only
tailscale serve --bg 8000                                    # https://<machine>.<tailnet>.ts.net
```

Only devices on your tailnet can reach it, and `tailscale serve` provides the https certificate.
Create the first account with `motionproof account create` as above.

## Frontend on Vercel, backend elsewhere

`vercel.json` deploys only the web app (the Vite build in `frontend/`) to Vercel and sends every
`/api/*` request on to your own backend, so the browser sees one site and the cookies work as
before. The backend still has to run somewhere else (a computer behind a tunnel, a VPS; see above).

**The backend cannot run on Vercel.** Its Python dependencies take about 1.07 GB installed
(measured on a Windows install: VTK 327 MB, CasADi 242 MB, OpenCascade 160 MB, LLVM 121 MB, SciPy
99 MB, MuJoCo 59 MB), and Vercel limits a Python function to 500 MB uncompressed. Vercel functions
also have no persistent disk (the workspace holds the accounts and every project) and are not built
for simulations that take minutes. A two-service setup (`app` + `frontend`) would fail at build.

Steps:

1. Run the backend as described above, with `--production`, reachable over https at a **stable**
   address (a Tailscale Funnel name or a VPS host name; a Cloudflare quick tunnel changes each
   time). Create the first account there with `motionproof account create`.
2. In `vercel.json`, replace `REPLACE-WITH-YOUR-BACKEND-HOST` in the `/api` rewrite with that host
   name (the file cannot read environment variables).
3. Tell the backend which site may send requests to it, in its environment, then restart it:
   `MOTIONPROOF_ALLOWED_ORIGINS=https://your-project.vercel.app` (add your own domain if you use
   one). Without it the backend refuses sign-in with "cross-origin request refused", because the
   browser's `Origin` is the Vercel address while the request reaches the backend under its own host
   name.
4. In Vercel, import the repository. Leave the framework preset on "Other": the install and build
   commands and the `frontend/dist` output come from `vercel.json`. If the build complains about
   the Node version, set Node 22 or newer in Project Settings.

`vercel.json` also sets the same security headers and Content-Security-Policy the backend sends,
for the pages Vercel serves itself. `.vercelignore` keeps the Python project out of the upload.

What has **not** been tested: a real deployment (the build was run locally and produces 505 files,
43.5 MB, but nothing was deployed), that session cookies pass through Vercel's rewrite, and
uploads of large CAD files through it (Vercel may limit the size of a proxied request; if it
does, uploads fail and need another route). Also, behind Vercel the backend sees Vercel's addresses
rather than each visitor's, so its per-address limits (failed sign-ins, new accounts) are shared by
everyone; the per-account lockout still applies.

## Backups

The whole state is the workspace folder (`/var/lib/motionproof/workspace`): the databases
(`auth.db`, `motionproof.db`), every project, and the per-account folders under `users/`. Copy it
somewhere else every day. SQLite files must be copied consistently, so use its own backup command
rather than copying them while the server runs:

```bash
sudo -u motionproof sqlite3 /var/lib/motionproof/workspace/auth.db ".backup /var/backups/motionproof/auth.db"
sudo -u motionproof sqlite3 /var/lib/motionproof/workspace/motionproof.db ".backup /var/backups/motionproof/motionproof.db"
sudo rsync -a --exclude '*.db' /var/lib/motionproof/workspace/ /var/backups/motionproof/files/
```

Keep at least one copy off the server, and try a restore once.

## Updating

```bash
cd /opt/motionproof && sudo -u motionproof git pull && sudo -u motionproof -H uv sync --locked
cd frontend && sudo -u motionproof -H npm ci && sudo -u motionproof -H npm run build && cd ..
sudo systemctl restart motionproof
```

Run the project's tests (`uv run pytest`) on a copy before updating a server people depend on, and
read `CHANGELOG.md`. Dependabot proposes dependency updates, and CI fails if a known
vulnerability is found in them.

## What this does not protect against

* **Uploaded CAD, mesh and scan files** are read by native libraries (OpenCascade, trimesh). A
  crafted file could crash a job or, in the worst case, exploit a flaw in them. That is why the
  service runs as an unprivileged user with a read-only system and why accounts should belong to
  people you trust.
* **Heavy use.** Each account is limited to 4 queued or running jobs and one simulation worker
  runs at a time by default, but there is no per-account CPU or disk quota.
* **No second factor, no email verification and no password reset by email.** The administrator
  resets passwords (Settings, or `motionproof account reset-password`).
* **The per-address limits** (failed sign-ins, new accounts) are kept in memory and start again
  when the server restarts. The per-account lockout is stored and survives a restart.
* **Cloud AI** sends results summaries to the provider you choose (see `docs/ai-assistant.md`).
* The first administrator is whoever creates the first account, so create it yourself before the
  server is reachable, and keep registration closed.

Report a vulnerability privately to the project owner before publishing details (`SECURITY.md`).
