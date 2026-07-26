# Database migration notice (2025)

Audience: all engineering.
Date: 2025-09-30.

## What changed

The shared database server `db.internal` was decommissioned at the end of September 2025.
Its hardware was end of life and the box has been powered off and unracked.
The database now runs locally on the backend host itself, listening on 127.0.0.1:5432.

## Action required

Any config, script, or cron job that still references the old host `db.internal` must be updated.
For services on the backend host the correct database address is now `127.0.0.1`.
The hostname `db.internal` no longer resolves to any machine, so stale references fail with connection errors rather than reaching a database.

## Verification

After updating a config, restart the affected service and confirm it can query the database.
Contact the platform team if you find any system still pointing at `db.internal`.
