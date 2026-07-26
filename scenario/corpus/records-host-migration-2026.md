# Records host migration notice (2026)

Audience: all clinical IT and site engineering.
Date: 2026-04-30.

## What changed

The shared records server `db-primary.cedarhollow.internal` was decommissioned at the end of April 2026.
The hardware was end of life and the box has been powered off and unracked.
Records now run locally on each clinic's own backend host, listening on 127.0.0.1:5432.

This was done to keep patient data inside each site's network rather than crossing the inter-site link.

## Action required

Any config, script, or scheduled job still referencing `db-primary.cedarhollow.internal` must be updated.
For services running on a clinic backend host, the correct records address is now `127.0.0.1`.

The hostname `db-primary.cedarhollow.internal` no longer resolves to any machine.
Stale references therefore fail at DNS resolution rather than reaching a records service, which surfaces as name resolution errors in the application log rather than connection refusals.

## Verification

After updating a config, restart the affected service and confirm it can complete a records lookup.
Contact site engineering if you find any system still pointing at the retired host.
