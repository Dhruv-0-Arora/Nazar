# Ticket 2026-05-133: build host out of disk

Opened: 2026-05-20 by site engineering.
Status: resolved.

## Symptoms

Builds on the site build host began failing with write errors.
No clinical system was affected; the build host serves no patient traffic.

## Investigation

Old build artifacts under the workspace directory had accumulated to fill the partition.
The cleanup job had been disabled during an earlier upgrade and never re-enabled.

## Resolution

Cleared artifacts older than 30 days and re-enabled the cleanup job.
Added a disk usage alert at 85 percent.
