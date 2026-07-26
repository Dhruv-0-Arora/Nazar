# Runbook: backend service configuration

Audience: anyone operating the Acme inventory backend.
Last reviewed: 2026-02.

## Where the config lives

The backend reads all of its connection settings from an env file: `backend.env`.
On production machines it is deployed at `/etc/myapp/backend.env`.
The service loads it at startup only, so config edits require a restart.

## Keys

- `PORT` - HTTP listen port for the API, normally 3001.
- `DB_HOST` - hostname or IP of the database the backend connects to.
- `DB_PORT` - database TCP port, normally 5432.
- `LOG_FILE` - path of the application log the backend appends to.

## Applying a change

Edit the file, then restart the service:

    sudo systemctl restart backend

Check `systemctl status backend` and the application log afterwards to confirm the startup INFO line shows the config you expect.
