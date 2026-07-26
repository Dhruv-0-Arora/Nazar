# Runbook: backup policy

Audience: site engineering.
Last reviewed: 2026-02.

## Schedule

Records are snapshotted nightly at 02:00 local time by the `clinic-backup` timer.
Snapshots are retained for 30 days on site and 12 months at the regional facility.
Application logs are not part of the records backup and rotate separately.

## Verifying a backup

Check `systemctl status clinic-backup.timer` and the last run result.
A failed timer does not affect patient lookups; the portal and records service are independent of the backup path.

## Restore

Restores are coordinated with the regional team and are never performed during clinic hours.
