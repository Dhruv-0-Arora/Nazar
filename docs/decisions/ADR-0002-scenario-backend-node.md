# ADR-0002: Scenario backend is Node

Status: accepted (needs scenario owner's ack).

## Context

PLAN.md is inconsistent: line 3 says "the crashing node app", line 20 says "minimal backend (Python/Flask or Node)".

## Decision

The scenario backend is a minimal Node/Express service, one endpoint hitting a DB (or mock DB), configured via `backend.env`.
The scenario frontend is a static page or tiny app calling it.

## Rationale

- PLAN's own bug list is Node-flavored ("Node app crashes", broken JSON parsing edge cases).
- Node is already installed on the machines.
- It keeps the language split clean: everything broken is Node, everything diagnostic is bash + Python. A Flask scenario backend would blur "the patient" and "the doctor" during the demo pitch.

## Consequences

- `inject.sh` targets `scenario/backend`'s env file (deployed at a fixed path, e.g. `/etc/myapp/backend.env`) and restarts its systemd unit.
- The collector must capture that env file under `services/backend/config/` per CONTRACT.md.
