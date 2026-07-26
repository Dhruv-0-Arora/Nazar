# Ticket 2025-05-197: CI runner out of disk space

Opened: 2025-05-22 by the build team.
Status: resolved.

## Symptoms

Nightly builds failed with "no space left on device" on the CI runner.
Daytime builds usually passed because the cleanup cron had run by then.

## Investigation

Docker image layers from abandoned feature branches had accumulated for months.
The runner's 200 GB disk was 97 percent full.

## Resolution

Added a weekly `docker system prune` job and a disk usage alert at 80 percent.
Freed 120 GB immediately.

## Lesson

Build infrastructure needs the same disk hygiene as production.
