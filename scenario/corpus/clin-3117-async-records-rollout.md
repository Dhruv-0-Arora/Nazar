# CLIN-3117: async records rollout, paused

Audience: site engineering.
Status: paused.
Last updated: 2026-05-22.

## What this is

CLIN-3117 replaces the backend's direct per-request call to the records service with a pooled async client.
The implementation landed in `backend/pool.js` behind the `FEATURE_ASYNC_RECORDS` flag.

## Why it is paused

Load testing at the Southgate site surfaced three defects, tracked together as CLIN-3204:

- The eviction sweep can exceed `DB_POOL_MAX` under burst load.
- `acquire()` has a check-then-act window; two concurrent acquisitions can take the same slot.
- The reaper interval is never cleared on shutdown, so the process holds a timer after `SIGTERM`.

Under sustained load these produced intermittent lookup failures and `connection pool saturated` lines in the application log.

## Current state

`FEATURE_ASYNC_RECORDS=false` in every site config, which is the shipped default.
With the flag off, the backend takes the direct-request path and nothing in `pool.js` executes.
The `DB_POOL_*` keys are still present in `backend.env` and are read only by the paused code.

Do not enable the flag at any site until CLIN-3204 lands.

## Note for on-call

Pool-related warnings in the application log can only originate from the flagged path.
If you see one at a site running the shipped default, treat the log line as suspect before treating the pool as the cause.
