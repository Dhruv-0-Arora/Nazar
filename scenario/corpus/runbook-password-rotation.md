# Runbook: password and secret rotation

Audience: all engineering.
Last reviewed: 2026-03.

## User passwords

Corporate passwords must be rotated every 12 months or immediately after a suspected compromise.
MFA is mandatory on every account, so routine forced rotation is deliberately infrequent.

## Service secrets

- API tokens rotate every 90 days via the secrets manager.
- Database credentials rotate every 180 days during a maintenance window.
- TLS certificates renew automatically 30 days before expiry.

## Emergency rotation

On suspected leakage, rotate the affected secret first and investigate second.
Record every emergency rotation in the security log with a link to the incident.
Never paste secrets into chat or tickets, even expired ones.
