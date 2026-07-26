# Ground truth - grading key

NEVER DEPLOY THIS FILE TO CLIENT MACHINES.
It is the answer sheet; if it lands in a bundle the demo grades itself.
`deploy/install.sh` deliberately never copies it, and it must not be placed under `/opt/company-docs/` on any laptop.

## Root cause

The backend's env file (`backend.env`, deployed at `/etc/myapp/backend.env` on laptop A) contains a stale database host: `DB_HOST=db.internal`.
The host `db.internal` was decommissioned in the 2025 database migration (see `corpus/db-migration-2025.md`); the database now runs locally on the backend host at `127.0.0.1:5432`.
Every `GET /api/items` therefore fails its TCP connection to `db.internal:5432` and returns 500, while `systemctl` still reports the backend service as active (running).
The frontend on laptop B shows "BACKEND UNAVAILABLE" for every poll, which is the symptom, not the cause.
The bug is planted by `inject.sh` and removed by `revert.sh`.

## What a correct diagnosis must contain

- The env var: `DB_HOST` (value `db.internal` is stale/wrong).
- The file: `backend.env` (at `/etc/myapp/backend.env` in the systemd deployment, `scenario/backend/backend.env` locally).
- The dangling host: `db.internal` no longer resolves to any machine; the database moved to `127.0.0.1` on the backend host in the 2025 migration.
- Cited evidence: the backend log's `ERROR db connect failed: connect ... db.internal:5432` lines, the `DB_HOST=db.internal` line in the collected config, and ideally the migration notice doc from laptop B (`db-migration-2025.md`) - that citation is the cross-machine synthesis the demo is built around.

## Expected fix effect

Set `DB_HOST=127.0.0.1` in the backend env file and restart the backend (`systemctl restart backend`, or kill/relaunch in local mode).
After the fix, `GET /api/items` returns 200 with rows and the frontend panel goes green.
Per ADR-0010, grade the Brain's `proposed_fix_script` on whether it substantially matches this effect; `revert.sh` is the trusted reference implementation, never the Brain's output.

## Grading notes

- Full marks: names DB_HOST, backend.env, identifies db.internal as decommissioned/dangling, cites both the log error and the config line, and proposes 127.0.0.1 plus a restart.
- Partial: blames "database down" or "connection refused" without tracing it to the stale config value.
- Fail (near-miss trap): blames a firewall rule blocking port 3001, which is the planted past incident `ticket-2025-03-frontend-502.md`, not this incident.
