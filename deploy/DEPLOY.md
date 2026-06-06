# Deploying Paradigm to the web

Battle-tested single-VM deployment (first run: Hetzner CPX31, Ubuntu 24.04, root,
behind Caddy with a shared password). Architecture rationale:
[`../.planning/WEB-DEPLOYMENT.md`](../.planning/WEB-DEPLOYMENT.md). Every step
below is what actually worked, with the gotchas we hit folded in.

```
https ─▶ Caddy (:443, TLS + basic-auth)
          • serves the built SPA  (frontend/dist)
          • proxies /api/* AND /health  ──▶  uvicorn backend (127.0.0.1:8000, 1 proc, systemd)
            (WebSocket /api/v1/sessions/*/ws rides on /api/*)        │
                                                                     ▼
                                              SQLite + ChromaDB on /var/lib/paradigm/data
                                              Docker sandbox (--network=none) for code execution
```

**Key facts that drive everything below**
- The frontend is **static** — Caddy serves `frontend/dist`; there is no second web server.
- Backend is a **single** uvicorn process (sessions are in-memory → no `--workers`).
- Caddy must proxy **both `/api/*` and the root `/health`** (the UI health-checks `/health`).
- The WebSocket is same-origin under `/api/*` (no separate port).
- Cycles persist + resume, so a backend restart is survivable; a *live* run is not.

---

## 0. Prerequisites
- A VM with **Docker** (we used Hetzner CPX31, 4 vCPU / 8 GB, Ubuntu 24.04).
- A domain/subdomain with an **A record → the VM IP** (e.g. `paradigm.stellarphysics.org`).
- Firewall: **22, 80, 443** open. Verify DNS from your laptop: `dig +short <domain>` → the IP.
- API keys ready: **`ANTHROPIC_API_KEY`**, **`GEMINI_API_KEY`** (production.yaml uses both).

## 1. System packages
```bash
apt update && apt upgrade -y          # if a new kernel installs: reboot, reconnect

# Python venv module — Ubuntu ships python3.12 but NOT the venv package:
apt install -y python3.12-venv        # (skipping this => "ensurepip is not available")

# Node — needed for the frontend build; NOT installed by default:
curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt install -y nodejs

# Docker — the code-execution sandbox:
curl -fsSL https://get.docker.com | sh && docker run --rm hello-world

# Caddy — reverse proxy + automatic TLS:
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy
```

## 2. Get the code (at /opt/paradigm)
```bash
git clone git@github.com:matteocantiello/paradigm.git /opt/paradigm
cd /opt/paradigm
```
Use **`/opt/paradigm`** — the systemd unit and Caddyfile reference that path. (If you
clone elsewhere, edit the paths in `deploy/paradigm-backend.service` + the Caddyfile.)

## 3. Python backend env + install
```bash
python3 -m venv .venv && . .venv/bin/activate     # prompt shows (.venv)
pip install -e ".[api,mcp,openai]"
```
The **extras matter**: `api` = FastAPI/uvicorn (the web server), `openai` = the Gemini
provider (OpenAI-compatible), `mcp` = alphaXiv literature. `anthropic` + `chromadb`
are core deps. (Installing just `.[mcp]` leaves you with **no uvicorn**.)

## 4. Build the sandbox image (code execution) — REQUIRED for experiments
Without this image, experiments are skipped ("paradigm-sandbox:latest not found").
The Dockerfile has no COPY, so use `docker/` as the context (avoids sending the
whole repo). Takes a few minutes (installs numpy/scipy/astropy/emcee/lmfit/…):
```bash
docker build -t paradigm-sandbox:latest -f docker/Dockerfile.sandbox docker/
docker images | grep paradigm-sandbox     # confirm it exists
```
No backend restart needed — the executor looks the image up per run.

## 5. Build the frontend (Caddy serves this folder)
```bash
cd /opt/paradigm/frontend && npm ci && npm run build && cd ..
ls frontend/dist/index.html           # must exist
```
Run `npm` from **`frontend/`**, not the repo root (else `ENOENT … package.json`).

## 6. Data dir + secrets
```bash
mkdir -p /var/lib/paradigm/data
cp deploy/.env.production.example deploy/.env.production
nano deploy/.env.production
chmod 600 deploy/.env.production
```
Fill `deploy/.env.production`:
```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
PARADIGM_CONFIG=configs/production.yaml
PARADIGM_DATA_DIR=/var/lib/paradigm/data
PARADIGM_CORS_ORIGINS=https://paradigm.stellarphysics.org
PARADIGM_MAX_CONCURRENT_SESSIONS=3
```
**This file must exist** — without it the backend boots with no keys and the wrong
config (a run would fail on auth). Optional alphaXiv literature: from a machine where
you ran `paradigm mcp-login`, `scp -r ~/.paradigm/mcp/ root@<vm>:/root/.paradigm/`.

## 7. Run the backend with systemd
```bash
nano deploy/paradigm-backend.service   # set User=root and Group=root for now (harden later)
cp deploy/paradigm-backend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now paradigm-backend
sleep 5                                 # give uvicorn time to import + bind
systemctl status paradigm-backend       # Active: active (running), uptime NOT resetting
curl -sS localhost:8000/health          # {"status":"ok","service":"paradigm-api"}
```
`enable --now` = start now + on every boot; `Restart=always` = auto-restart on crash.
If `status` shows `failed` or a resetting uptime: `journalctl -u paradigm-backend -n 50 --no-pager`.

## 8. Point Caddy at Paradigm (replaces the default "congrats" page)
```bash
caddy hash-password                     # type a password → COPY the $2a$... hash
```
Write `/etc/caddy/Caddyfile` (overwrite the default welcome config entirely):
```
paradigm.stellarphysics.org {
	encode gzip zstd

	# Shared-password gate (one line per person).
	basic_auth {
		science $2a$14$PASTE_YOUR_HASH
	}

	# API + WebSockets + the root /health probe -> backend.
	# /health is at the ROOT, not under /api — list it too, or the UI shows "API offline".
	@api path /api/* /health
	handle @api {
		reverse_proxy 127.0.0.1:8000
	}

	# Built SPA + client-side routing.
	handle {
		root * /opt/paradigm/frontend/dist
		try_files {path} /index.html
		file_server
	}
}
```
```bash
caddy validate --config /etc/caddy/Caddyfile      # expect "Valid configuration"
systemctl reload caddy
journalctl -u caddy -n 20 --no-pager              # watch it obtain the TLS cert
```
(Caddy ≥ 2.8 uses `basic_auth`; older uses `basicauth` — `validate` will tell you.)

## 9. Verify end-to-end
```bash
curl -sS -u science:YOURPASSWORD https://<domain>/health   # {"status":"ok",...}
```
Open **https://<domain>** → password prompt → Paradigm → header shows **API Online** →
start a run → it streams live and reaches a paper.

---

## Gotchas we actually hit (symptom → fix)
| Symptom | Cause | Fix |
|---|---|---|
| `ensurepip is not available` | venv pkg missing | `apt install -y python3.12-venv`, recreate the venv |
| `pip: command not found` | venv not activated | the venv didn't create; fix the line above, then `. .venv/bin/activate` |
| `No module named uvicorn` / no web server | installed only `.[mcp]` | `pip install -e ".[api,mcp,openai]"` |
| `npm error … ENOENT … package.json` | ran from repo root | `cd /opt/paradigm/frontend` first |
| systemd service `failed` / `User=paradigm` doesn't exist | unit expects a `paradigm` user | set `User=root`/`Group=root` for now (or create the user) |
| `curl -s` prints nothing | `-s` hides connection errors; backend still starting | use `curl -sS` / `-v`; `sleep 5` after `enable --now` |
| Caddy "congratulations" page | Caddy on its default config | replace `/etc/caddy/Caddyfile` (step 8) + reload |
| **"API offline"** in the UI | Caddy only proxied `/api/*`, not `/health` | matcher must be `@api path /api/* /health` |
| Run stuck **"connecting"** / no streaming | old build hardcoded `:8000` in the WS URL | `git pull` + rebuild frontend (step 5); WS now uses the same origin |
| Run errors with an auth message | wrong/missing key | fix `deploy/.env.production` → `systemctl restart paradigm-backend` |
| `502 Bad Gateway` | backend not on `:8000` | `systemctl status paradigm-backend` / journal |
| Fresh clone won't build (`utils.ts` missing) | a `lib/` gitignore rule once hid `frontend/src/lib` | already fixed in repo; `git pull` if on an old clone |

---

## Operating it
- **Update:**
  ```bash
  cd /opt/paradigm && git pull
  . .venv/bin/activate && pip install -e ".[api,mcp,openai]"   # if deps changed
  cd frontend && npm ci && npm run build && cd ..               # if frontend changed
  systemctl restart paradigm-backend                            # if backend changed
  systemctl reload caddy                                        # if the Caddyfile changed
  ```
  A backend restart drops any *live* run, but cycles persist and reappear as
  **Interrupted** in the research tab → hit **Resume**.
- **Logs:** `journalctl -u paradigm-backend -f` (backend) · `journalctl -u caddy -f` (proxy).
- **Backup** (the only sensible cron job) — nightly snapshot of the data dir:
  ```bash
  crontab -e
  0 3 * * * tar czf /root/paradigm-backup-$(date +\%F).tgz /var/lib/paradigm/data
  ```
  Restore: stop the service, replace `/var/lib/paradigm/data`, start it.
- **Concurrency / cost:** `PARADIGM_MAX_CONCURRENT_SESSIONS` caps simultaneous runs;
  per-thread token budgets live in `configs/production.yaml`.
- **Disable code execution:** set `orchestrator.enable_experimentation: false` in
  `configs/production.yaml` → `systemctl restart paradigm-backend`.

## Hardening (do AFTER it's working — not mid-build)
- Create a non-root user, add to the `docker` group, `chown -R` the dirs, and set the
  service `User=`/`Group=` to it (least-privilege for the sandbox).
- Use a **strong** basic-auth password (the URL is public and spends real LLM money).
  Rotate via `caddy hash-password` → edit the Caddyfile → `systemctl reload caddy`.
- Disable root SSH (`PermitRootLogin no`), key-only auth, and enable `ufw` (22/80/443).
- The sandbox is `--network=none` + `cap_drop=ALL` + `no-new-privileges` + pids/cpu/mem/
  timeout caps — strong for a *trusted* group, but not a hard multi-tenant boundary.
  Don't open this profile to the anonymous public.
