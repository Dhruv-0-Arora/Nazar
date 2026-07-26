# Runbook: guest wifi access

Audience: reception and IT.
Last reviewed: 2025-11.

## Network

Guests use the `Acme-Guest` SSID, which is isolated from the corporate LAN.
The guest VLAN only allows outbound HTTP, HTTPS, and DNS.

## Issuing access

- Reception creates a voucher in the wifi portal, valid for one day.
- For multi-day visitors, IT can issue a voucher valid up to two weeks.
- Vouchers are single device; a second device needs a second voucher.

## Troubleshooting

If a guest cannot connect, confirm the voucher has not expired and the device count.
The captive portal requires the browser to try a plain HTTP site first.
Escalate to IT if the portal itself does not load, since that usually means the portal VM is down.
