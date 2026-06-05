# Deploying Paradigm to the web

Single-VM deployment for a small trusted group behind a shared password.
Architecture + rationale: [`../.planning/WEB-DEPLOYMENT.md`](../.planning/WEB-DEPLOYMENT.md).

```
https ─▶ Caddy (:443, TLS + basic-auth) ─▶ uvicorn backend (:8000, 1 proc)
          serves frontend/dist            SQLite+ChromaDB on /var/lib/paradigm
          proxies /api + /ws              spawns Docker sandbox (--network=none)
```

## 1. Provision the VM
- A Linux VM with **Docker** (recommend Hetzner CPX31 — 4 vCPU/8 GB — or a DO 8 GB droplet).
- Point a DNS **A record** (e.g. `paradigm.example.com`) at the VM's IP.
- Install: Docker, Caddy, and Python 3.12 (or Miniconda). Create a `paradigm` user
  and add it to the `docker` group: `sudo usermod -aG docker paradigm`.

## 2. Get the code + build
```bash
sudo mkdir -p /opt/paradigm && sudo chown paradigm:paradigm /opt/paradigm
git clone <repo> /opt/paradigm && cd /opt/paradigm

# Backend env (venv shown; conda also fine)
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[mcp]"

# Code-execution sandbox image
docker build -f docker/Dockerfile.sandbox -t paradigm-sandbox:latest .

# Frontend (served statically by Caddy; same-origin so no API URL needed)
cd frontend && npm ci && npm run build && cd ..

# Persistent data dir (survives restarts; back this up)
sudo mkdir -p /var/lib/paradigm/data && sudo chown paradigm:paradigm /var/lib/paradigm/data
```

## 3. Secrets + config
```bash
cp deploy/.env.production.example deploy/.env.production
$EDITOR deploy/.env.production         # fill keys, domain, data dir, concurrency
chmod 600 deploy/.env.production
```
alphaXiv literature (optional but recommended): run `paradigm mcp-login` **once on a
machine with a browser**, then copy the cached token to the VM:
```bash
scp -r ~/.paradigm/mcp/ paradigm@<vm>:~/.paradigm/      # token auto-refreshes after
```

## 4. Run the backend (systemd)
```bash
sudo cp deploy/paradigm-backend.service /etc/systemd/system/
# adjust ExecStart if using conda; confirm User= and paths
sudo systemctl daemon-reload && sudo systemctl enable --now paradigm-backend
systemctl status paradigm-backend          # should be active; check `journalctl -u paradigm-backend`
curl -s localhost:8000/health              # {"status":"ok",...}
```

## 5. Run Caddy (TLS + password gate)
```bash
cp deploy/Caddyfile /etc/caddy/Caddyfile
$EDITOR /etc/caddy/Caddyfile                # set your domain + dist path
caddy hash-password                         # paste the bcrypt hash per collaborator
sudo systemctl reload caddy                 # Caddy fetches the TLS cert automatically
```

## 6. Smoke test
Open `https://paradigm.example.com`, authenticate, start a short run, and confirm:
live panels stream, the terminal screen appears at the end, and Resume works.

---

## Operating it
- **Update**: `git pull` → rebuild frontend (`npm run build`) → `sudo systemctl restart
  paradigm-backend` → `sudo systemctl reload caddy`. (A restart drops any *live* run,
  but cycles persist and show as **Interrupted** → Resume them.)
- **Backups**: nightly copy/snapshot of `/var/lib/paradigm/data` (SQLite + `chroma`).
  Restore = stop service, replace dir, start.
- **Rotate a password**: edit the Caddyfile `basic_auth` block → `systemctl reload caddy`.
- **Concurrency / cost**: `PARADIGM_MAX_CONCURRENT_SESSIONS` caps simultaneous runs;
  per-thread token budgets are in `configs/production.yaml`. Watch usage in the DB/events.
- **Disable code execution**: set `orchestrator.enable_experimentation: false` in
  `configs/production.yaml` and restart.

## Security notes (read before exposing)
- Code runs in the sandbox (`--network=none`, `cap_drop=ALL`, `no-new-privileges`,
  pids/cpu/mem/timeout caps). Strong for a TRUSTED group; **not** a hard multi-tenant
  boundary — don't open to the public on this profile.
- The shared password is the only gate; prefer per-collaborator credentials and rotate.
- Keep the VM patched; restrict SSH; only 80/443 (+ SSH) should be open.
