# Runbook: password rotation

Audience: all staff.
Last reviewed: 2025-12.

## Policy

Staff passwords rotate every 180 days.
Service account credentials rotate annually and are held in the site credential vault.
Shared front-desk accounts are not permitted.

## Rotating a service account

- Open a change ticket before rotating anything a running service depends on.
- Update the vault entry first, then the consuming config, then restart the service.
- Confirm the service recovered before closing the ticket.

## Lockouts

Five failed attempts lock an account for fifteen minutes.
Reception cannot unlock accounts; escalate to IT.
