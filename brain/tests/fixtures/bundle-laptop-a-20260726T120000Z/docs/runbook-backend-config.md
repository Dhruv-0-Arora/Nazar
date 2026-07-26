# Backend configuration runbook

Backend DB connection settings live in the env file at /etc/myapp/backend.env on the backend host.

## Keys

- DB_HOST: database hostname or IP
- DB_PORT: database port, default 5432

## Applying changes

After editing the env file, restart with: systemctl restart backend
