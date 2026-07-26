# Ground truth - grading key

NEVER DEPLOY THIS FILE TO CLIENT MACHINES.
It is the answer sheet; if it lands in a bundle the demo grades itself.
`deploy/install.sh` never copies it, `scripts/nuke.sh` deletes it, and it must not be placed under `/opt/company-docs/` on any laptop.

## Root cause

The backend's env file (`backend.env`, deployed at `/etc/clinic/backend.env` on laptop A) contains a stale records host: `DB_HOST=db-primary.cedarhollow.internal`.
That host was decommissioned in the April 2026 records migration (see `corpus/records-host-migration-2026.md`); records now run locally on each clinic's backend host at `127.0.0.1:5432`.
Every `GET /api/patients` therefore fails DNS resolution and returns 502, while `systemctl` still reports `clinic-backend` as active (running) and `/healthz` still returns 200.
The portal on laptop B shows its failure card for every lookup, which is the symptom, not the cause.
The fault is planted by `inject.sh` and removed by `revert.sh`.

## What a correct diagnosis must contain

- The env var: `DB_HOST` (value `db-primary.cedarhollow.internal` is stale).
- The file: `backend.env` (at `/etc/clinic/backend.env` in the systemd deployment, `scenario/backend/config/backend.env` locally).
- The dangling host: it no longer resolves; records moved to `127.0.0.1` on the backend host in the 2026 migration.
- Cited evidence: the `ERROR ... err=ENOTFOUND upstream=db-primary.cedarhollow.internal:5432` lines in the application log, the `DB_HOST=` line in the collected config, and ideally the migration notice from laptop B - that citation is the cross-machine synthesis the demo is built around.

## Expected fix effect

Set `DB_HOST=127.0.0.1` in the backend env file and restart the service.
After the fix, `GET /api/patients` returns 200 with 12 records and the portal renders the patient table.
Grade a proposed fix on whether it substantially matches this effect.
`revert.sh` is the trusted reference implementation and is never the Brain's output.

## Grading bands

**Full marks.**
Names `DB_HOST`, names `backend.env`, identifies the host as decommissioned rather than merely unreachable, cites both the log error and the config line, and proposes `127.0.0.1` plus a restart.

**Partial.**
Blames "records database down" or "DNS failure" without tracing it to the stale config value, or proposes the right fix without citing evidence.

## Fail traps

The scenario plants deliberate distractors.
A diagnosis that lands on any of these is wrong, and which one it lands on tells you what the retrieval or reasoning got wrong.

- **Firewall.** Blames a rule blocking port 8080. That is the planted past incident `ticket-2026-03-portal-errors.md`, not this one. Indicates the agent matched on symptom similarity rather than current evidence.
- **Connection pool.** Blames the three real concurrency defects in `backend/pool.js`. That file is dead code behind `FEATURE_ASYNC_RECORDS=false`; nothing in it executes. Indicates the agent read code without tracing the execution path. `corpus/clin-3117-async-records-rollout.md` states the flag is off at every site, so the evidence to rule this out is present and retrievable.
- **Legacy host.** Proposes `DB_HOST_LEGACY=10.0.4.7` as the fix. That key is read by nothing and is retained for a rollback path. Indicates the agent found the right file but the wrong line.
- **TLS certificate.** Blames the expiry warning in the log. The records service accepts plaintext on the clinic VLAN and the certificate is never presented.
- **Cache disabled.** Blames `CACHE_TTL_SECONDS=0`. There is no cache in the codebase.

All five distractors are inert and all five are present in a healthy bundle as well as a faulted one.
An agent that flags any of them while the system is healthy is producing a false positive, which is worth measuring separately.

See `BREAKAGE.md` for the full catalogue and the rule every distractor satisfies.
