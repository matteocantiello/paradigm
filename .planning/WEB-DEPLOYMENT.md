# Web Deployment Plan

**Goal:** make Paradigm reachable from the web for **a small trusted group**, via a
**public HTTPS URL gated by a shared password**, hosting choice left to recommendation.

This is a planning document — no code has changed. Effort estimate: ~1 focused day
to first working deploy (Phases 0–2), plus hardening (Phase 3) as needed.

---

## TL;DR recommendation

**One small cloud VM, everything on the host, Caddy in front.**

```
            ┌────────────────────────── VM (Ubuntu + Docker) ──────────────────────────┐
  you ──────┤  Caddy (:443)                          uvicorn backend (:8000, 1 process) │
  https     │   • auto-TLS (Let's Encrypt)   ──/──▶   • FastAPI + WebSockets            │
            │   • basic-auth (shared pw)              • SQLite + ChromaDB on local disk  │
            │   • serves frontend  static            • spawns sandbox containers ──┐     │
            │   • proxies /api + /ws                                               ▼     │
            │                                          Docker sandbox (--network=none)   │
            └───────────────────────────────────────────────────────────────────────────┘
```

**Why this shape (driven by the platform's constraints):**
- The **code sandbox needs Docker on the host** → a plain VM beats most PaaS.
- **Sessions are in-memory** → a single uvicorn process (no `--workers`); a VM is the natural single-node home (cycles persist + resume now, so a restart is survivable).
- **SQLite + ChromaDB are local files** → one disk + backups, no managed DB needed.
- **Run the backend ON the host, not in a container.** If the backend runs in a
  container and spawns sandbox containers via the Docker socket, bind-mount paths
  resolve on the *host*, not the backend container → the classic sibling-container
  path mismatch. On-host backend uses host Docker + host paths directly. (Caddy can
  still be a container or a host service — it doesn't touch the sandbox.)

**Recommended host:** Hetzner Cloud **CPX31** (4 vCPU / 8 GB, ~€15/mo) or a
DigitalOcean 8 GB droplet (US regions if latency matters). Size up if you expect
several concurrent cycles (each cycle + its sandbox competes for CPU/RAM).

---

## What's already deployment-ready (no work)
- **CORS** via `PARADIGM_CORS_ORIGINS`.
- **Auth hook**: `X-API-Key` + `PARADIGM_API_KEY` (off when unset).
- **Frontend**: prod `build` (`tsc -b && vite build`); API base via `VITE_API_BASE_URL`,
  WS base via `VITE_WS_BASE_URL` (same-origin fallback) → works behind `wss://`.
- **Sandbox limits**: `network_mode=none`, `memory_limit`, `cpu_limit`, `execution_timeout`.
- **alphaXiv MCP** runs headless from a cached token.

## Gaps to close (the actual work)
1. **No reverse proxy / TLS / auth gate** — add Caddy.
2. **No concurrency or cost cap** — a few users × 20-min cycles can swamp the VM and
   balloon the LLM bill. Add a `max_concurrent_sessions` cap (small SessionManager
   change) + keep the per-thread token budgets.
3. **Secrets on a server** — API keys via an env file (gitignored, `chmod 600`);
   alphaXiv token: copy `~/.paradigm/mcp/alphaxiv/` from a machine where you ran
   `paradigm mcp-login` (headless VM can't open a browser).
4. **Sandbox hardening for shared use** — keep `network=none`; add `pids_limit`,
   `cap_drop=ALL`, read-only rootfs where feasible; conservative cpu/mem/timeout.
5. **Persistence/ops** — data on a backed-up volume; systemd auto-restart; health check.
6. **No deploy artifacts** — add a Caddyfile + a run recipe (systemd unit or compose).

---

## Phased plan

### Phase 0 — Decisions & prereqs (you)
- [ ] Pick host (recommend Hetzner CPX31 or DO 8 GB) + region.
- [ ] A domain/subdomain (e.g. `paradigm.<yourdomain>`); point an A record at the VM.
- [ ] Decide the shared password(s) — recommend one basic-auth credential per
      collaborator (revocable individually) rather than a single shared secret.
- [ ] Confirm: keep **code execution enabled** for the web deploy? (Powerful but the
      main risk surface. Could ship experiments-disabled first, enable later.)

### Phase 1 — Make it deployable (code/config) ✅ DONE
- [x] **Concurrency + cost cap**: `SessionManager.max_concurrent_sessions` +
      `at_capacity()`; both start points (start_session, resume) return **429** when
      full. Overridable via `PARADIGM_MAX_CONCURRENT_SESSIONS`. +tests.
- [x] **Sandbox hardening**: `pids_limit`, `cap_drop=ALL`, `no-new-privileges`,
      optional read-only rootfs in `sandbox/docker.py` + `SandboxConfig` (safe defaults).
- [x] **Frontend build**: served same-origin by Caddy → no API/WS URL env needed
      (relative `/api`, WS derives from origin). Build step in DEPLOY.md.
- [x] **Secrets**: `deploy/.env.production.example` (real one gitignored) + `.paradigm/`
      ignored; alphaXiv token-copy documented.
- [x] **`deploy/Caddyfile`**: auto-TLS + `basic_auth` + serve `frontend/dist` +
      reverse_proxy `/api/*` (WS transparent).
- [x] **`deploy/paradigm-backend.service`**: single-process uvicorn, `Restart=always`,
      runs as a `docker`-group user; backend on host (avoids the sandbox path gotcha).
- [x] **`configs/production.yaml`**: fast models, **non-blocking gates** (`human_gate_mode:
      off`), streaming on, mcp on, experiments on (hardened) with a one-line disable toggle.
- [x] **`deploy/DEPLOY.md`** runbook (provision → build → secrets → run → smoke test → operate).

### Phase 2 — Provision & deploy (~half day)
- [ ] Spin up VM, install Docker + Caddy + the conda/py env (or a venv).
- [ ] Clone repo, build the sandbox image (`docker build -f docker/Dockerfile.sandbox`).
- [ ] `npm ci && npm run build` the frontend.
- [ ] Drop `.env.production` + the alphaXiv token dir; set DNS.
- [ ] Start uvicorn (systemd) + Caddy; Caddy fetches TLS automatically.
- [ ] **Smoke test**: log in over HTTPS, run a short cycle end-to-end (watch the live
      panels, the terminal screen, and a resume).

### Phase 3 — Harden & operate (ongoing)
- [ ] **Backups**: nightly snapshot of the data dir (SQLite + `chroma`); document restore.
- [ ] **Monitoring**: external uptime check on `/health`; log rotation; basic alerting.
- [ ] **Cost guardrails**: watch token usage (events/DB); per-day or per-user caps if needed.
- [ ] **Runbook**: deploy/update, rotate a password, restore from backup, rebuild sandbox.
- [ ] **Defense in depth (optional)**: also set `PARADIGM_API_KEY` so the API requires a
      key even if the proxy is bypassed (frontend injects it).

---

## Security checklist & residual risks
- ✅ TLS everywhere (Caddy) · ✅ password gate (Caddy basicauth) · ✅ CORS locked to the domain.
- ✅ Sandbox `network=none` + cpu/mem/pids/timeout limits + cap_drop.
- ⚠️ **Code execution**: trusted users can run arbitrary code in the sandbox. Isolation
  is `--network=none` + resource caps + an unprivileged container — strong but not a
  hard multi-tenant boundary. Acceptable for a *trusted* group; revisit before public.
- ⚠️ **Shared credentials**: rotate periodically; prefer per-user basicauth creds.
- ⚠️ **Single VM = single point of failure**: backups make it recoverable, not HA.
- ⚠️ **Cost**: a gated-but-shared URL still lets any logged-in user spend tokens — the
  concurrency cap + budgets are the brakes.

## Explicitly out of scope (would need the "public/multi-user" path)
Per-user accounts & data isolation, horizontal scaling (blocked by in-memory sessions —
would need externalized session state), a hardened multi-tenant sandbox, autoscaling.

## Open decisions to confirm before building
1. Host: **Hetzner CPX31** (recommended) vs DigitalOcean vs an existing AWS/GCP account.
2. Domain/subdomain to use.
3. Keep code-execution enabled on day one, or ship experiments-disabled first?
4. Human-gate for remote use: keep blocking phase gates, or switch to non-blocking +
   rely on the steering bar (better for unattended remote runs)?
5. Backend runtime: **systemd on host** (recommended, avoids the sandbox path gotcha)
   vs docker-compose (more reproducible, but needs careful socket + path handling).
