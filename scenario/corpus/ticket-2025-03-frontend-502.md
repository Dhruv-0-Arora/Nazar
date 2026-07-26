# Ticket 2025-03-114: frontend showing errors for all users

Opened: 2025-03-18 by helpdesk.
Status: resolved.

## Symptoms

The inventory dashboard on the frontend machine showed a red error panel for every request.
The backend host itself looked healthy and `systemctl status backend` reported active (running).
Users assumed the backend had crashed, but the process was up the whole time.

## Investigation

We first suspected the backend application and spent an hour reading its logs, which showed nothing unusual.
The real problem was on the network path: a leftover iptables rule on the backend host was blocking inbound TCP port 3001.
The frontend's proxy requests never reached the backend at all.

## Resolution

Removed the stray firewall rule blocking port 3001 and reloaded iptables.
The dashboard recovered immediately with no service restart needed.

## Lesson

When the frontend errors out but the backend service reports running, check the firewall rules on the backend host early.
