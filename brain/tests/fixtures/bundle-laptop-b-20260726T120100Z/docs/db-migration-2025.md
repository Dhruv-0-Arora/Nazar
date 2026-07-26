# Database migration 2025

The shared database host db.internal was decommissioned in June 2025.

The database now runs locally on each backend host and listens on 127.0.0.1:5432.

Any service configs still referencing db.internal must be updated to 127.0.0.1.
