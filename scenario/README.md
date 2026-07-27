# Scenario package (M0)

Cedar Hollow Community Health, patient records portal.
The deliberately broken three-service system the Brain diagnoses, plus its planted knowledge base.

**Synthetic data only.**
Every patient record is fabricated.
No real person, MRN, or clinical event is represented.

## Port map

| Service | Port | Where |
|---|---|---|
| `clinic-backend` | 8080 | laptop A |
| `clinic-mockdb` | 5432 | laptop A, same host as the backend |
| `clinic-portal` | 3000 | laptop B |

## What this package carries

- `backend/` - the patient. Node HTTP service, config from `/etc/clinic/backend.env`, logs to `/var/log/clinic/backend.log`.
- `mockdb/` - the records service. Serves `patients.json` over HTTP. See `mockdb/README.md`.
- `frontend/` - the symptom. Serves the portal and calls the backend from the browser.
- `corpus/` - 13 authored markdown docs plus `placement.json` with disjoint per-laptop sets.
- `deploy/` - systemd units and `install.sh` for the two-laptop setup.
- `scripts/inject.sh` / `scripts/revert.sh` - plant and remove the fault, both idempotent.
- `scripts/build.sh` / `scripts/deploy.sh` - build the artifact and stage host layouts.
- `scripts/nuke.sh` - strip a deployed copy of every hint, then verify the strip.
- `ground_truth.md` - grading key. Never deploy to client machines.
- `BREAKAGE.md` - the fault catalogue and the distractor rules.

## This replaced an earlier scenario package

The previous package used an Acme inventory domain on ports 3001/8080 with paths under `/opt/myapp`.
Its history is intact in git if any of it is wanted back.

Two things changed that readers of the older docs should know:

- **Ports moved.** Backend is 8080 (was 3001) and the portal is 3000 (was 8080).
- **Paths moved.** `/opt/clinic` and `/etc/clinic` (were `/opt/myapp` and `/etc/myapp`).

`collector/collector.sh` still searches the legacy `/etc/myapp/` and
`/var/log/myapp/` paths alongside the clinic ones, so old deployments keep
collecting.

## Why a clinic

Config-only bugs break it credibly, the failure is visually obvious on a
projector, the corpus docs write themselves as clinic runbooks and tickets, and
it makes the HIPAA answer concrete — the demo shows PHI never leaving the
building, which is what a judge asked about directly.

## Zero dependencies, on purpose

Node stdlib only at runtime. No `package.json` runtime deps, no webfonts, no CDN
(the only dev dependency is `esbuild`, used by `scripts/build.sh` on the build
host, never on a clinic machine).
The scenario premise is a dead network — anything that needs `npm install` or a
font request on-site breaks the story, and a hanging font request would quietly
prove the box still has internet.

## Topology

```
laptop A                                laptop B
┌────────────────────────────┐          ┌──────────────────┐
│ clinic-mockdb   :5432      │          │ clinic-portal    │
│   patients.json            │          │   :3000          │
│         ▲                  │          │        │         │
│         │ DB_HOST:DB_PORT  │          │        │ BACKEND_URL
│ clinic-backend  :8080      │◄─────────┼────────┘         │
│   /etc/clinic/backend.env  │          └──────────────────┘
│   /var/log/clinic/backend.log         
└────────────────────────────┘
```

Two config values are the bug surface: **`DB_HOST`** on the backend (primary
scenario) and **`BACKEND_URL`** on the portal (frontend-side variant).

## The symptom chain

This is the whole point of the scenario, and it is verified working:

| # | Check | Healthy | Bugged |
|---|---|---|---|
| 1 | process / `systemctl status` | active (running) | **active (running)** |
| 2 | `curl /healthz` | `200 ok` | **`200 ok`** |
| 3 | `curl /api/patients` | `200`, 12 records | **`502 records_database_unreachable`** |
| 4 | app log | `INFO patient query served` | **`ERROR ... err=ENOTFOUND upstream=db-primary.cedarhollow.internal:5432`** |

Rows 1 and 2 staying green is deliberate. `/healthz` is shallow by design and
`db.js` opens its connection **per request, never at boot** — a boot-time
reachability check would crash the service and give the bug away for free.

Observed bugged output:

```
HTTP 502
{"error":"records_database_unreachable","code":"ENOTFOUND",
 "upstream":{"host":"db-primary.cedarhollow.internal","port":5432},
 "correlationId":"342e773c","detail":"getaddrinfo ENOTFOUND db-primary.cedarhollow.internal"}

2026-07-26T20:49:21.420Z ERROR [clinic-backend] records database unreachable \
  cid=342e773c err=ENOTFOUND upstream=db-primary.cedarhollow.internal:5432 \
  detail="getaddrinfo ENOTFOUND db-primary.cedarhollow.internal" ms=42
```

**The identifiers on the portal screen are the identifiers in the app log.**
Error class, upstream `host:port`, correlation ID — all three appear in both
places verbatim. That is what lets the FDE read a string off the screen and the
agent cite the same string out of the bundle. Don't prettify them.

## Run it locally

```bash
scripts/run-local.sh          # healthy
scripts/run-local.sh broken   # stale DB_HOST, reproduces the outage
```

Portal at <http://127.0.0.1:3000>, backend at <http://127.0.0.1:8080>, app log
at `.local/logs/backend.log`. Ctrl-C stops all three.

Single-laptop dev topology only — demo day splits across two machines under
systemd.

## Layout

```
mockdb/server.js          stands in for the records DB; serves patients.json
mockdb/patients.json      12 synthetic records
backend/server.js         patient API; shallow /healthz, /api/meta, /api/patients
backend/db.js             per-request upstream client — where the bug manifests
backend/logger.js         append-only file log; format is load-bearing for the chunker
backend/config/backend.env  deploys to /etc/clinic/backend.env — inject.sh edits this
frontend/server.js        static server + generated /config.json
frontend/public/          the portal UI
scripts/run-local.sh      dev runner; seeds .local/backend.env so inject/revert work locally
scripts/inject.sh         plant the outage (idempotent, 4 bug variants)
scripts/revert.sh         restore healthy (idempotent, no-op when clean)
scripts/nuke.sh           strip a DEPLOYED copy of every hint, then verify
BREAKAGE.md               full catalogue of what breaks and how hard each is
```

## Break it and fix it

```bash
ENV_FILE=.local/backend.env scripts/inject.sh     # default: stale DB_HOST
#   restart run-local.sh (systemd does this for you on a real box)
ENV_FILE=.local/backend.env scripts/revert.sh     # back to healthy
```

Deployed paths are the defaults — `/etc/clinic/backend.env`, unit
`clinic-backend`, restarted via `systemctl`. `ENV_FILE` / `SERVICE` / `DATA_FILE`
override for local work. Both scripts are idempotent: repeat injects don't
corrupt the pristine backup, and revert on a clean system is a no-op.

Bug variants: `--bug stale-host` (default) · `empty-env` · `bad-port` ·
`malformed-db`. See `BREAKAGE.md`.

## Before evaluating the agent: nuke

The scripts above, this README, and the source comments all name the bug. Left
on the box, the agent reads the answer instead of diagnosing. `nuke.sh` strips a
**deployed copy** down to evidence only:

```bash
scripts/nuke.sh --target /opt/clinic             # dry run, lists everything
scripts/nuke.sh --target /opt/clinic --yes       # then type NUKE
scripts/nuke.sh --target /opt/clinic --verify    # audit, changes nothing
```

It deletes the hint files, backups, `.git`, and dev artifacts, then scrubs
comments containing scenario language from every text format on the box. Then it
re-runs `--verify` and reports PASS/FAIL, including a check that **the fault
itself survived** — a nuke that also removes the bug leaves nothing to diagnose.

Two guards: it refuses to run inside the source tree, and `--yes` alone isn't
enough — you must type `NUKE`. Deletion is irreversible and unbacked.

## Portal UI notes

Institutional healthcare software on purpose: dense, cool, squared off, system
fonts. Monospace carries every machine identifier (MRN, host, error class,
correlation ID) — how real EHRs display them, and what makes the failure state
legible from across a war room.

The failure card is the designed centerpiece, not the header. It states what
broke, names both services, and shows the diagnostic block verbatim. It does not
apologize and does not say "something went wrong."

Three mutually exclusive regions — `#loading`, `#records`, `#failure` — plus a
fixed status bar that always names the upstream and the last successful read.
The status bar distinguishes **portal can't reach backend** (`EPORTAL`) from
**backend can't reach database** (`ENOTFOUND`), which are different outages and
must not look the same on screen.

