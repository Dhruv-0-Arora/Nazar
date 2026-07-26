# Scenario package (M0)

The deliberately broken two-machine system the Brain diagnoses, plus its planted knowledge base.
Everything runs on Node core modules only (`http`, `net`, `fs`, `path`); there are zero npm dependencies and nothing to install on the client laptops beyond Node itself.

## Port map

| Service | Port | Where |
|---|---|---|
| backend | 3001 | laptop A |
| frontend | 8080 | laptop B |
| mock-db | 5432 | laptop A (same host as the backend) |

## Layout

- `backend/` - the patient: Node HTTP service, config from `backend.env` (`ENV_FILE` env var overrides the path), logs to `backend.log`.
- `mock-db/` - "the database": trivial TCP banner server on 5432 (`MOCK_DB_PORT` overrides).
- `frontend/` - the symptom: serves `index.html` and proxies `/api/*` to `BACKEND_URL` (no CORS), logs proxy errors to `frontend.log`.
- `corpus/` - 12 authored markdown docs plus `placement.json` (disjoint per-laptop doc sets, see OPEN-QUESTIONS #6).
- `deploy/` - systemd units and `install.sh` for the two-laptop setup.
- `inject.sh` / `revert.sh` - plant and remove the bug, both idempotent.
- `ground_truth.md` - grading key; never deploy to client machines.

## Run locally (one machine, development)

```
./run-local.sh     # starts mock-db (5432), backend (3001), frontend (8080)
./stop-local.sh    # stops all three
```

Pidfiles (`<name>.pid`) and process logs (`<name>.out.log`) land next to each server.
Overrides: `FRONTEND_PORT=8090 ./run-local.sh` if 8080 is taken; `MOCK_DB_PORT=6432 ./run-local.sh` if 5432 is taken, but then also set `DB_PORT=6432` in `backend/backend.env` so the backend looks in the right place.
Check health: `curl http://127.0.0.1:3001/api/health` and `curl http://127.0.0.1:8080/api/items`.

## Inject and revert the bug

```
./inject.sh    # sets DB_HOST=db.internal in backend/backend.env, restarts backend
./revert.sh    # sets DB_HOST=127.0.0.1, restarts backend
```

Both edit only the `DB_HOST` line and are safe to run twice.
In local mode they restart the backend through `backend/backend.pid` if it exists, otherwise they print start instructions.
With `--system` they edit `/etc/myapp/backend.env` and run `systemctl restart backend` instead (needs sudo).
After injection: `/api/health` still returns ok, `systemctl` still says running, but `/api/items` returns 500 and `ERROR db connect failed: connect ... db.internal:5432` lines accumulate in the backend log.
That subtlety is the point.

## Deploy on two laptops

Requires sudo (writes to `/opt/myapp`, `/etc/myapp`, `/var/log/myapp`, `/etc/systemd/system`, `/opt/company-docs`).

```
# on laptop A (backend + mock-db + its corpus docs)
sudo ./deploy/install.sh laptop-a

# on laptop B (frontend + its corpus docs); point it at laptop A
sudo ./deploy/install.sh laptop-b http://<laptop-a-ip>:3001
```

`install.sh` copies the code to `/opt/myapp/`, writes env files to `/etc/myapp/` (backend log at `/var/log/myapp/backend.log`), enables the systemd units, and copies each laptop's corpus docs to `/opt/company-docs/` per `corpus/placement.json`.
It never copies `ground_truth.md` or `placement.json` onto a laptop.
Then break it with `sudo ./inject.sh --system` on laptop A and reset with `sudo ./revert.sh --system`.

## Corpus design

- `runbook-backend-config.md` (laptop A): the genuinely useful doc; says DB settings live in `backend.env` at `/etc/myapp/backend.env`.
- `ticket-2025-03-frontend-502.md` (laptop B): the near-miss; same symptoms, but that incident's cause was a firewall rule on port 3001.
- `db-migration-2025.md` (laptop B): the cross-machine synthesis doc; `db.internal` was decommissioned, the database moved to `127.0.0.1` on the backend host.
- 9 noise docs: unrelated tickets and generic runbooks.

The migration doc deliberately lives on the other machine from the bug, so a correct diagnosis requires joining evidence across both bundles.
