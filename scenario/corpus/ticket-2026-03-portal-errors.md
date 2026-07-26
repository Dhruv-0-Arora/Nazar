# Ticket 2026-03-241: portal showing errors for all front-desk users

Opened: 2026-03-11 by helpdesk.
Status: resolved.

## Symptoms

The patient records portal showed a red error panel for every lookup at the North Clinic front desk.
The backend host itself looked healthy and `systemctl status clinic-backend` reported active (running).
`/healthz` returned 200 the entire time.
Staff assumed the backend had crashed, but the process was up throughout.

## Investigation

We first suspected the backend application and spent about an hour reading its logs, which showed nothing beyond the usual advisory warnings.
The real problem was on the network path: a leftover nftables rule on the backend host was dropping inbound TCP port 8080.
The portal's requests never reached the backend at all.

## Resolution

Removed the stray firewall rule blocking port 8080 and reloaded nftables.
The portal recovered immediately with no service restart needed.

## Lesson

When the portal errors out but the backend service reports running, check the firewall rules on the backend host early.
A green `/healthz` does not prove the service is reachable from another machine, only that the process is alive on its own host.
