# Ticket #4412 (2025-03): frontend returning 502

Users reported the frontend showing errors for all requests.

Investigation showed the backend was healthy but unreachable from the frontend host.

Root cause: a firewall rule on the backend host was blocking inbound port 3001.

Resolution: removed the iptables rule and requests recovered immediately.
