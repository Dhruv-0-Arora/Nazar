# Ticket 2026-01-019: VPN dropouts for remote staff

Opened: 2026-01-08 by IT.
Status: resolved.

## Symptoms

Remote staff were disconnected from the VPN every 30 to 40 minutes.
Only remote users were affected; on-site clinical systems were unaffected throughout.

## Investigation

The VPN concentrator's session lifetime had been set to 30 minutes during a maintenance window and never restored.
Reconnects were succeeding, which is why the issue read as a network fault rather than a config change.

## Resolution

Restored the session lifetime to eight hours.
Dropouts stopped immediately.

## Lesson

Check what changed during the last maintenance window before investigating the network.
