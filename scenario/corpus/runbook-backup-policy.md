# Runbook: backup policy

Audience: platform team.
Last reviewed: 2025-12.

## What is backed up

- File shares: nightly incremental, weekly full.
- Databases: nightly dump plus continuous WAL archiving.
- Laptops: user directories synced to the cloud drive, not centrally backed up.

## Retention

- Nightly backups are kept for 30 days.
- Weekly fulls are kept for 6 months.
- Year-end fulls are kept for 7 years for compliance.

## Restore drills

A restore drill runs on the first Monday of each quarter.
The drill restores one database and one file share to a scratch host and verifies checksums.
Failures open a P2 ticket automatically.
