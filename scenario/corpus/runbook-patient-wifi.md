# Runbook: patient and visitor wifi

Audience: reception and IT.
Last reviewed: 2026-01.

## Network

Patients and visitors use the `CedarHollow-Guest` SSID, isolated from the clinical VLAN.
The guest VLAN allows outbound HTTP, HTTPS, and DNS only.
No clinical system is reachable from it, by design of the network segmentation policy.

## Issuing access

- Reception issues a voucher from the wifi portal, valid for one day.
- For patients in extended care, IT can issue a voucher valid up to two weeks.
- Vouchers are single device; a second device needs a second voucher.

## Troubleshooting

If a patient cannot connect, confirm the voucher has not expired and check the device count.
The captive portal requires the browser to attempt a plain HTTP site first.
Escalate to IT if the portal itself does not load, which usually means the portal VM is down.
