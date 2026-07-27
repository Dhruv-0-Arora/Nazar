# collector

`collector.sh` is the client-side collector (M2).
It is a single dependency-free bash script (bash + coreutils; `ip`/`ss`/`systemctl`/`journalctl`/`iptables`/`nft` are optional) that produces a diagnostic bundle conforming to CONTRACT.md v1.0.

## Usage

```
./collector.sh [-o <outdir>] [--services "a b c"] [--docs <dir>] [--push <brain-host>] [--notes "text"]
```

| Flag | Default | Meaning |
|---|---|---|
| `-o <outdir>` | `~/bundles` | where the bundle directory is written |
| `--services "a b"` | `"backend frontend"` | space-separated service names to collect |
| `--docs <dir>` | `/opt/company-docs` | doc corpus copied into `docs/` (`.md` files only) |
| `--push <host>` | off | scp push mode (see transport modes below) |
| `--notes "text"` | empty | free-text note recorded in `manifest.json` |

Environment variable `EXTRA_PATHS` (space-separated file paths) adds ad-hoc captures; each lands as `app_logs/<basename>` (last 500 lines).

The script is idempotent and safe to run as non-root; commands that are missing or fail still emit their `### CMD: ... ###` marker followed by an `unavailable: <reason>` line.
Every run creates a new `bundle-<machine_id>-<timestamp>/` directory and never clobbers a previous one.

## Config discovery per service `<name>`

1. Env-file candidates, first match wins: `/etc/myapp/<name>.env` (legacy),
   `/etc/clinic/<name>.env`, and for namespaced units like `clinic-backend`
   also `/etc/clinic/<short-name>.env` (e.g. `backend.env`).
2. `/etc/<name>/*` - non-recursive; regular, readable, text files only.

App logs are tailed from `/var/log/myapp/*.log` and `/var/log/clinic/*.log`.
Copies land under `services/<name>/config/<original-filename>`.
A service with no systemd unit and no config still gets its directory, with `status.txt` containing `unavailable: no such service`.

## Transport modes (ADR-0003)

1. SSH pull (primary): run the collector with no `--push`; the bundle sits in `<outdir>` and the operator runs `brain pull <host>` on the Brain.
2. scp push (fallback): `--push <brain-host>` scp's the bundle into `<brain-host>:~/brain/inbox/.staging/` and then atomically `mv`'s it into `~/brain/inbox/` over ssh.
3. USB (tertiary): copy the bundle directory onto a stick and run `brain ingest <path>` on the Brain.
   The FDE client stick under `transport-layer/usb-transport/` is a separate flow: its `main.sh` collects into the stick's `outbox/`, and the Brain's USB intake (`brainctl usb`, `POST /api/usb/receive`, or the watcher's auto-scan) verifies and normalizes those bundles on arrival (CONTRACT.md section 5).

All routes deposit contract-identical bundles; the contract is the interface, not the transport.

## Size caps

No file exceeds 512 KB (truncated from the top, tail kept, `"truncated": true` recorded in the manifest) and the total bundle stays under 5 MB.
Binary files are skipped.
