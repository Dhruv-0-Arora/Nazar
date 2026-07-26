# ADR-0003: Three transport modes, one bundle contract

Status: accepted.

## Context

PLAN C1 defines two modes (Brain SSH/scp pull primary, client scp push fallback).
PLAN M2 separately describes a USB-stick flow ("fits on a USB stick", copy the working folder onto the stick, carry it to the Brain).
These were never unified.

## Decision

Three ranked modes, all depositing byte-identical bundles per CONTRACT.md:

1. SSH pull (primary): the operator runs `brain pull <host>` on the Brain, which scp's the manifest first, then the whole bundle, from the client's `~/bundles/` output directory. Default demo path.
2. scp push (fallback): last lines of collector.sh push to the Brain's inbox staging area.
3. USB (tertiary): operator carries the bundle directory; `brain ingest <path>` on the Brain performs the atomic deposit.

Deposits are atomic: copy into `inbox/.staging/`, then rename into `inbox/`.
The direct-ethernet-cable option from PLAN C1 is not a fourth mode; it is mode 1 or 2 with static IPs, a connectivity choice not an architecture choice.

## Rationale

- The inbox watcher must not be able to tell transports apart; the contract fixes the interface so transport stays swappable.
- The staging + rename protocol closes a race PLAN never addressed: the watcher observing a half-copied bundle.
- USB earns its place in the pitch (works when the network is fully cooked) at the cost of one small `brain ingest` command.

## Consequences

- collector.sh needs a `--push <brain-host>` flag; without it, the bundle just sits locally for pull or USB.
- Pre-demo checklist (SSH keys both directions, inbox permissions, dry-run scp) stays as written in PLAN C1.
