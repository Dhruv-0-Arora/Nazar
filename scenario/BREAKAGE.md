# Breakage catalogue

Everything this scenario can break, what it looks like from each vantage point,
and how hard it is for an agent to find. **Do not ship this file to a client
machine** — `scripts/nuke.sh` deletes it.

## Design rule every bug obeys

The service must stay **`active (running)`** and `/healthz` must stay **200**.
A bug that crashes the process is a bug an FDE finds in ten seconds with
`systemctl`, and proves nothing. Every bug here is a *config-plane* fault that
leaves the control plane looking healthy — which is exactly the class of outage
that eats an hour of war-room time.

Two mechanisms make that possible, both deliberate:
- `backend/db.js` opens its upstream connection **per request, never at boot**
- `backend/server.js` `/healthz` is **shallow** — it never probes the database

## The catalogue

| # | Bug | Injected by | Surface | Error class | Where it's visible |
|---|---|---|---|---|---|
| 1 | **Stale `DB_HOST`** — points at a decommissioned host | `inject.sh` (default) | `/etc/clinic/backend.env` | `ENOTFOUND` | app log, `/api/patients` 502, portal failure card |
| 2 | **Empty `DB_HOST`** — key present, value blank | `inject.sh --bug empty-env` | `/etc/clinic/backend.env` | `ECONFIG` | same three, message differs |
| 3 | **Wrong `DB_PORT`** — nothing listening | `inject.sh --bug bad-port` | `/etc/clinic/backend.env` | `ECONNREFUSED` | same three |
| 4 | **Malformed records JSON** — truncated file | `inject.sh --bug malformed-db` | `mockdb/patients.json` | `EHTTP500` | mockdb stderr + backend app log |
| 5 | **Stale `BACKEND_URL`** — portal points at a moved backend | manual / env | portal env | `EPORTAL` | portal only; backend is perfectly healthy |
| 6 | **Upstream hang** — DB reachable, never answers | firewall DROP rule | network layer | `ETIMEDOUT` | app log, 3s latency then 502 |

Bugs 1–4 are scripted. 5 and 6 are wired in code (`db.js` and `app.js` already
return those codes) but need a host-level action to trigger — 5 is an env edit
on laptop B, 6 is an `iptables`/`nft` DROP rule.

## Difficulty ladder

Ordered by how much reasoning the agent has to do, not by severity.

**Tier 1 — single-machine, single-file.** Bugs 1–3. The env file and the app log
are in the same bundle; the error line literally names the bad host. An agent
that reads the ERROR line and the config chunk should get this. This is the
demo's happy path — **use bug 1**.

**Tier 2 — cross-file synthesis.** Bug 4. The backend log says `EHTTP500`, which
is a *symptom*; the cause is in mockdb's stderr and the shape of
`patients.json`. The agent has to stop at the backend and keep walking upstream.

**Tier 3 — cross-machine synthesis.** Bug 5. Nothing on laptop A is wrong. The
backend's own logs are clean and its `/healthz` is green. The evidence lives in
laptop B's bundle while the *reported* symptom ("records won't load") comes from
a user at laptop B looking at a portal that can't reach laptop A. Requires two
bundles and the `talks_to` graph edge to solve. **This is the bug that justifies
the graph layer** — BM25 alone will keep dredging up laptop A's healthy logs.

**Tier 4 — no application evidence at all.** Bug 6. The firewall rule is in
`network.txt`, not in any log. The app log shows only `ETIMEDOUT`. The agent has
to correlate a timeout against a DROP rule it finds in a completely different
file kind. Hardest, most realistic, most likely to fail. Keep it as the stretch
demo.

## What each vantage point sees (bug 1)

| Vantage | Output |
|---|---|
| `systemctl status clinic-backend` | `active (running)` — **no signal** |
| `curl /healthz` | `200 {"status":"ok"}` — **no signal** |
| `curl /api/patients` | `502 records_database_unreachable`, `code: ENOTFOUND` |
| app log | `ERROR ... err=ENOTFOUND upstream=db-primary.cedarhollow.internal:5432 cid=…` |
| journal | same line (logger writes both) |
| portal UI | failure card: error class, upstream, correlation ID, timestamp |
| `/etc/clinic/backend.env` | `DB_HOST=db-primary.cedarhollow.internal` |

The **correlation ID and upstream host appear in the app log and on the portal
screen verbatim.** That shared string is what lets the FDE read something off a
projector and the agent cite the same token out of the bundle.

---

# Red herrings

Things that look like the cause and are not. **Every one is inert** — it changes
no behaviour — and every one is present in the **healthy** bundle as well as the
faulted one. That second property is what makes them herrings: anything that only
shows up during the outage correlates with it, and correlation is the agent's job
to exploit. These must not correlate.

## In the log

Emitted by `backend/maintenance.js` on a 45s timer, from boot, always.

| Line | Why it baits | Why it's inert |
|---|---|---|
| `records service certificate expires soon path=/etc/clinic/tls/records.pem` | TLS + records service + a deadline reads as an auth or handshake failure | The records service accepts plaintext on the clinic VLAN. Nothing presents this cert. Expiry is fixed at 2026-08-14. |
| `record cache disabled, every lookup goes to the records service ttl=0` | Suggests load or a thundering herd on the upstream | There is no cache in the codebase at all. `CACHE_TTL_SECONDS` is read once, here, and nowhere else. |
| `legacy records endpoint still enabled, scheduled for removal in 2.6 endpoint=/api/patients` | Names the exact endpoint that is failing, and calls it legacy | Advisory only. `/api/v2/records` does not exist. |
| `application log exceeds retention window and is not being rotated` | Disk pressure reads as a cause | Only fires if the log file is older than 30 days. Advisory. |
| `connection pool saturated, request queued` | The most convincing one — resource exhaustion, on the upstream, at the right moment | Unreachable. Emitted only from `pool.js`, which only runs when `FEATURE_ASYNC_RECORDS=true`, which is `false` in every config. |

## In the config

`/etc/clinic/backend.env` carries five inert keys:

| Key | Bait | Reality |
|---|---|---|
| `DB_HOST_LEGACY=10.0.4.7` | A **second, different** database host. An agent that finds the real `DB_HOST` wrong may "fix" it to this. | Read by nothing. Retired pre-2025 addressing. |
| `DB_PORT_LEGACY=5432` | Reinforces the above | Read by nothing. |
| `FEATURE_ASYNC_RECORDS=false` | A disabled feature flag next to a broken feature invites "turn it on" | Turning it on routes through `pool.js` and makes things worse, not better. |
| `DB_POOL_MAX=8` / `DB_POOL_IDLE_MS` / `DB_POOL_REAP_MS` | Pool tuning knobs imply a pool is in play | Only read by the dead path. |
| `TLS_CERT_PATH` | Pairs with the cert warning | Read only by the maintenance reporter. |

## In the code

`backend/pool.js` — a full connection pool implementation with **three genuine,
findable bugs**, none of which can execute:

1. **Off-by-one in `reap()`** — `i <= this.connections.length` walks one past the
   end of the live set
2. **Check-then-act race in `acquire()`** — an `await` sits between the
   availability test and the checkout, so two concurrent acquires can take the
   same slot
3. **Reaper interval never cleared** on shutdown

The bugs are real. An agent reading this file will find them, and they are
exactly the kind of thing that causes intermittent upstream failures. They are
also **completely dead**: `db.js` only calls `fetchViaPool` when
`FEATURE_ASYNC_RECORDS === 'true'`, and it never is.

The comments cite ticket numbers (`CLIN-3117`, `CLIN-3204`, `CLIN-2988`) to make
the whole thing read as a real paused rollout rather than decoration.

**This is the hardest herring and the most valuable one.** A model that reasons
"there are three concurrency bugs in the connection pool, that's the root cause"
has produced a plausible, well-evidenced, completely wrong diagnosis — which is
precisely the failure mode we need to be able to detect. Grading must reward
tracing the actual execution path over finding the scariest-looking code.

## Host-level (stage these on the box; not code)

Not yet implemented — set up on the client machines before collection:

- a **failed unrelated unit** so `systemctl --failed` is non-empty
  (e.g. `clinic-backup.timer` failing on a missing mount)
- a partition at **91% full**
- a **stale lock file** at `/var/run/clinic/backend.lock` from a previous boot
- an unrelated process **listening on a nearby port** (5433)

## Rule for adding more

A herring is only valid if it satisfies all three:

1. **Inert** — removing it changes no behaviour
2. **Present when healthy** — it must appear in a clean bundle too
3. **Plausible** — a competent engineer would spend real time on it

Anything failing (2) is not a herring, it is a second symptom, and it makes the
outage *easier* to diagnose rather than harder.

---

## Corpus tuning

The fake corpus in `/opt/company-docs/` (authored in `corpus/`, placed per
`corpus/placement.json`) is written *against* the chosen bug so the agent has
to reason rather than string-match:

- **one near-miss** — e.g. `2025-03: portal 502s — root cause was a firewall
  rule`. Same symptom, wrong cause. Punishes an agent that pattern-matches "502"
  and stops.
- **one genuinely useful** — e.g. `runbook: backend DB connection settings live
  in /etc/clinic/backend.env`. Points at the right file without naming the answer.
- **noise** — unrelated tickets, generic runbooks, an on-call rota.

Place at least one useful doc on the *other* laptop, so solving it requires
merging two bundles.

## Grading

`ground_truth.md` holds the real root cause and what a correct
diagnosis must contain. It **never ships to a client machine**, and `nuke.sh`
removes it. A diagnosis passes if it names the config key, the file, the bad
value, and the fix — citing chunk IDs for each.
