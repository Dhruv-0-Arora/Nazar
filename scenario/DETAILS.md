# DETAILS — what this is and how to drive it

**Internal. Never ships to a client machine.** `scripts/nuke.sh` deletes this file.

---

## What this is

A deliberately breakable three-service system, standing in for a small clinic's
patient records stack. It is the **testbed** for a local-first incident-response
agent: we plant a realistic system-level fault, collect evidence off the box, and
grade whether the agent can find the root cause from that evidence alone.

It is not a product. Its only job is to fail in a way that is *hard but fair*.

## Why a clinic

Config-only faults break it credibly. The failure is legible on a projector. The
supporting document corpus writes itself as clinic runbooks and tickets. And it
makes the data-privacy story concrete: patient data never leaves the network,
which is the point of running the agent locally in the first place.

All patient data is fabricated. No real person or clinical event is represented.

## The three services

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

| Service | Port | Role |
|---|---|---|
| `clinic-mockdb` | 5432 | Serves `patients.json`. See `mockdb/README.md`. |
| `clinic-backend` | 8080 | Patient API. Reads `/etc/clinic/backend.env`. Writes the app log. |
| `clinic-portal` | 3000 | Browser UI. Reads `BACKEND_URL` at page load via `/config.json`. |

Two config values are the fault surface: **`DB_HOST`** on the backend and
**`BACKEND_URL`** on the portal.

## Zero dependencies, and why it matters

Node stdlib only. No `package.json` deps, no bundler, no webfonts, no CDN. The
premise is a network that is down — anything needing `npm install` or a font
request on-site cannot run, and a hanging font request would quietly prove the
box still has internet.

## The rule every fault obeys

The service stays **`active (running)`** and `/healthz` stays **200**. A fault
that kills the process is one an engineer finds in ten seconds with `systemctl`.
Every fault here leaves the control plane looking healthy while the data plane
fails — the class of outage that actually eats an hour.

Two mechanisms make that work, and both are load-bearing:

- `backend/db.js` opens its upstream connection **per request, never at boot**
- `backend/server.js` `/healthz` is **shallow** — it never touches the database

Adding a boot-time reachability check or a deep health probe would defeat the
whole exercise. Don't.

## The symptom chain

| # | Check | Healthy | Faulted |
|---|---|---|---|
| 1 | `systemctl status clinic-backend` | active (running) | **active (running)** |
| 2 | `curl :8080/healthz` | `200 ok` | **`200 ok`** |
| 3 | `curl :8080/api/patients` | `200`, 12 records | **`502 records_database_unreachable`** |
| 4 | app log | `INFO patient query served` | **`ERROR … err=ENOTFOUND upstream=…`** |

Error class, upstream `host:port`, and correlation ID appear **verbatim** in both
the app log and the portal's failure card. That shared token is what lets a human
read a string off the screen and the agent cite the same string out of collected
evidence. Do not prettify them.

---

# Setup

## Local, one machine

```bash
scripts/run-local.sh
```

Seeds `.local/backend.env` from `backend/config/backend.env` on first run, then
sources it — mirroring systemd's `EnvironmentFile=`, which is what makes the
break/fix cycle testable without two laptops.

- portal — <http://127.0.0.1:3000>
- backend — <http://127.0.0.1:8080/api/patients>
- app log — `.local/logs/backend.log`

`scripts/run-local.sh --fresh` discards local config and starts clean.
Ctrl-C stops all three.

## Deployed, two machines

Laptop A runs `clinic-mockdb` and `clinic-backend`; laptop B runs
`clinic-portal`. Deployed paths:

| Path | Contents |
|---|---|
| `/etc/clinic/backend.env` | Backend config — the file that gets edited |
| `/var/log/clinic/backend.log` | App log |
| `/opt/clinic/mockdb/patients.json` | Records file |
| `/opt/company-docs/` | Document corpus (M0 remainder) |

Set `BACKEND_URL` on laptop B to laptop A's address. systemd units are still to
be written.

---

# Dev loop: break it, then fix it

## Break

```bash
ENV_FILE=.local/backend.env scripts/inject.sh
```

Then restart `run-local.sh` — on a real box systemd does this for you.

| Flag | Fault | Error class |
|---|---|---|
| *(default)* `--bug stale-host` | `DB_HOST` → decommissioned host | `ENOTFOUND` |
| `--bug empty-env` | `DB_HOST` present but empty | `ECONFIG` |
| `--bug bad-port` | `DB_PORT` → nothing listening | `ECONNREFUSED` |
| `--bug malformed-db` | truncates `patients.json` | `EHTTP500` |

`--dry-run` prints what it would change and touches nothing.

**Idempotent.** Running it twice re-asserts the faulted value and leaves the
`.pristine` backup holding the *original* — repeat runs can't corrupt your
ability to recover.

## Fix

```bash
ENV_FILE=.local/backend.env scripts/revert.sh
```

Restores from `.pristine`, removes the backup, restarts. Running it on an
already-healthy system is a no-op that says so.

`revert.sh` is the reference fix, kept for resets between runs. It is **not** the
artifact the agent is meant to produce — the autofix milestone has the agent
write its own from the diagnosis. Don't hand this file to the agent.

## Deployed paths are the defaults

Both scripts default to `/etc/clinic/backend.env`, unit `clinic-backend`, and
restart via `systemctl`. Override with `ENV_FILE`, `SERVICE`, `DATA_FILE` for
local work. Without systemd they print a manual-restart reminder instead of
failing.

## Verify a break took

```bash
curl -s -o /dev/null -w '%{http_code}\n' :8080/healthz        # expect 200
curl -s -o /dev/null -w '%{http_code}\n' :8080/api/patients   # expect 502
grep ERROR .local/logs/backend.log | tail -1
```

If `/healthz` returns anything but 200, the fault is wrong — you've broken the
process rather than its config.

---

# nuke: strip the box before evaluating

## Why

`inject.sh` names the fault. `DETAILS.md` and `BREAKAGE.md` explain it. Source
comments describe it. Every one of those on the box means the agent reads the
answer instead of diagnosing it. Any evaluation run against an un-nuked copy is
worthless.

## What it does

Turns a **deployed copy** into an ordinary-looking service repo:

- deletes the tooling and internal docs — `inject.sh`, `revert.sh`,
  `run-local.sh`, `nuke.sh` itself, `DETAILS.md`, `BREAKAGE.md`,
  `ground_truth.md`, `placement.json`
- deletes backups and dev residue — `*.pristine`, `.local/`, `.runlog`, `.git/`
- scrubs comments containing internal language from every text format that ships
  (`.js`, `.sh`, `.css`, `.env`, `.conf`, `.service`, `.html`, `.yaml`, …)
- **writes a plain operations README in place of the internal one**, so what
  remains reads like a normal internal service repo rather than an emptied-out
  sandbox
- keeps `mockdb/README.md`, which is ordinary service documentation

The fault itself is left untouched. That's the thing being diagnosed.

## Usage

```bash
scripts/nuke.sh --target /opt/clinic             # dry run; lists every change
scripts/nuke.sh --target /opt/clinic --yes       # arms it; then type NUKE
scripts/nuke.sh --target /opt/clinic --verify    # audit only; changes nothing
```

Exit codes: `0` clean · `1` usage or refusal · `2` verify found surviving hints.

## Guards

1. **`--target` is required.** It will not guess.
2. **Dry run is the default.** `--yes` is needed to change anything.
3. **Typed confirmation.** `--yes` alone is not enough; you must type `NUKE`.
4. **Refuses inside the source tree.** If it can see the planning docs above
   `code/`, it stops — nuking your working copy would destroy the testbed.

Deletion is irreversible and unbacked. Run it on a deployment.

## Verify

`--verify` is also run automatically after a detonation. It checks three things:

- no hint **files** survive
- no internal **language** survives in any file's contents
- **the fault still exists** — a nuke that also removed the bug would leave
  nothing to diagnose, and that failure mode is silent otherwise

It prints `PASS` or `FAIL` with every surviving leak listed. Trust `--verify`
over the scrub: the scrubber works from an extension list, and a format missing
from that list is exactly how a hint survives. Verify greps everything.

---

# Still to build (M0 remainder)

- systemd units for all three services
- `/opt/company-docs/` corpus — one near-miss doc, one genuinely useful runbook,
  several noise docs, with at least one useful doc on the *other* laptop
- `ground_truth.md` — real root cause plus what a correct diagnosis must contain
- `placement.json` — which machine gets which fault and which docs

See `BREAKAGE.md` for the full fault catalogue and the difficulty ladder.
