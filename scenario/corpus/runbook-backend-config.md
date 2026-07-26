# Runbook: patient records backend configuration

Audience: anyone operating the Cedar Hollow records backend.
Last reviewed: 2026-06.

## Where the config lives

`clinic-backend` reads all of its connection settings from an env file: `backend.env`.
On clinic hosts it is deployed at `/etc/clinic/backend.env` and loaded by systemd as an `EnvironmentFile`.
The service reads it at startup only, so config edits require a restart.

## Keys

- `PORT` - HTTP listen port for the API, normally 8080.
- `DB_HOST` - hostname or IP of the records service the backend connects to.
- `DB_PORT` - records service TCP port, normally 5432.
- `DB_TIMEOUT_MS` - how long a records lookup waits before giving up.
- `LOG_FILE` - path of the application log the backend appends to.

Several other keys appear in the file and are not read by the running service.
`DB_HOST_LEGACY` and `DB_PORT_LEGACY` are retained for the CLIN-2988 rollback path.
The `DB_POOL_*` keys and `FEATURE_ASYNC_RECORDS` belong to the paused async rollout described in CLIN-3117.
`TLS_CERT_PATH` and `CACHE_TTL_SECONDS` are provisioned but inactive.

## Applying a change

Edit the file, then restart the service:

    sudo systemctl restart clinic-backend

Check `systemctl status clinic-backend` and the application log afterwards.
The startup INFO line reports the upstream the service actually resolved, which is the fastest way to confirm a change took effect.

## A note on health checks

`/healthz` reports process liveness only and does not contact the records service.
It returns 200 whenever the service is running, including while records lookups are failing.
Use `/api/meta` or the application log to confirm records access, never `/healthz` alone.
