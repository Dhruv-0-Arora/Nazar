# Ticket 2025-01-042: VPN dropouts for remote staff

Opened: 2025-01-14 by helpdesk.
Status: resolved.

## Symptoms

Remote staff reported the VPN disconnecting every 30 to 40 minutes.
Reconnecting worked immediately, which pointed away from credential problems.

## Investigation

The VPN concentrator's DHCP lease pool for remote clients was set to a 30 minute lifetime.
Renewals were being dropped by an MTU mismatch on the tunnel interface.

## Resolution

Raised the lease lifetime to 8 hours and clamped the tunnel MSS.
No dropouts reported since the change.

## Lesson

Session lifetimes that match the complaint interval are rarely a coincidence.
