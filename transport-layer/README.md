# transport-layer

USB stick tooling for when the network itself is the casualty.
`usb-transport/` has two halves:

## client/ — ships on the stick, runs on the sick machine

`main.sh` is the ONE script the FDE runs. Configuration is per device
(`collect-<machine_id>.conf` on the stick), so carrying the stick across
several laptops runs setup once on each new device and collects immediately
on devices already set up:

- First run on a device: `main.sh` starts `setup.sh`, which registers the
  problem folders / logs / services interactively (or via flags) and then
  automatically runs `collector.sh`.
- Later runs: skips setup, collects straight away.
- Windows machines use `setup.ps1` + `collector.ps1` (config in
  `collect.conf.json`).

Bundles from every device accumulate side by side in `outbox/` on the stick.

## workstation/ — runs on the Brain

`receive_bundle.py` discovers `bundle-*` directories at a source (stick,
staging dir), verifies each against its `manifest.json` (existence, byte
size, sha256), copies verified bundles into the Brain inbox, and writes a
`receipt.json`. It contains no indexing logic — transport ends when a
verified bundle sits in the inbox.

In practice the operator never runs it by hand: the Brain's USB intake
(`brainctl usb`, `POST /api/usb/receive`, or the watcher's auto-scan) wraps
it and normalizes each bundle to CONTRACT.md before the atomic deposit
(see CONTRACT.md section 5, "USB client-stick variant").

`atomic_transfer.py` is the stick-side deposit helper; its bundle-renaming
grammar mirrors `brain/src/brain/ingest/usb.py`.
