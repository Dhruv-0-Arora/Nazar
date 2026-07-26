# CONTRACT.md - Bundle Data Contract (v1.0)

This is the interface between the Client Collector (M2) and the Brain (M3/M4).
Both sides build against this file and nothing else.
Any change requires bumping `contract_version` and sign-off from both owners.

The same contract applies to every transport mode (SSH pull, scp push, USB copy).
Transport is swappable precisely because this contract fixes the interface.
See [ADR-0003](docs/decisions/ADR-0003-transport-modes.md).

## 1. Bundle naming

```
bundle-<machine_id>-<timestamp>/
```

- `machine_id`: lowercase hostname, matching `[a-z0-9-]+`.
  No colons, no dots, no underscores (the chunk ID grammar in section 6 depends on this).
- `timestamp`: UTC, `YYYYMMDDTHHMMSSZ` (e.g. `20260726T183000Z`).
- Example: `bundle-laptop-a-20260726T183000Z/`

The full directory name is the `bundle_id`.

## 2. Directory layout

```
bundle-<machine_id>-<ts>/
├── manifest.json          REQUIRED  machine identity + inventory (section 3)
├── system.txt             REQUIRED  command sections (section 4 delimiters)
├── network.txt            REQUIRED  command sections (section 4 delimiters)
├── processes.txt          REQUIRED  ps aux snapshot
├── packages.txt           OPTIONAL  recent package changes
├── services/
│   └── <service>/         one dir per collected service
│       ├── status.txt     REQUIRED  systemctl status output
│       ├── journal.txt    REQUIRED  last 200 journal lines
│       └── config/        REQUIRED  verbatim copies of config files
│           └── <original-filename>   e.g. backend.env
├── app_logs/
│   └── <name>.log         tail (last 500 lines) of each application log
└── docs/
    └── **/*.md            copy of /opt/company-docs/ from this machine
```

Rules:

- Everything is UTF-8 text. The collector must skip binary files.
- No file may exceed 512 KB. The collector truncates from the top (keep the tail) and records `"truncated": true` in the manifest.
- Total bundle size must stay under 5 MB.
- Paths inside the bundle must not contain `:` or newline characters (chunk ID grammar).
- Empty directories are allowed (e.g. `docs/` on a machine with no corpus docs).

## 3. manifest.json schema

```json
{
  "contract_version": "1.0",
  "bundle_id": "bundle-laptop-a-20260726T183000Z",
  "machine_id": "laptop-a",
  "hostname": "laptop-a",
  "created_at": "2026-07-26T18:30:00Z",
  "os": "Ubuntu 24.04.2 LTS",
  "kernel": "6.8.0-45-generic",
  "collector_version": "1.0.0",
  "services": ["backend"],
  "files": [
    {"path": "system.txt", "bytes": 4210, "truncated": false},
    {"path": "services/backend/config/backend.env", "bytes": 312, "truncated": false}
  ],
  "notes": ""
}
```

- `services` lists the service names collected under `services/`.
- `files` is the complete inventory of every file in the bundle except `manifest.json` itself.
  This is what tells the Brain what it is looking at before (or without) walking the tree, and what enables selective fetch later.
- `notes` is free text typed by whoever ran the collector (optional symptom description).

## 4. Command-output delimiters

`system.txt` and `network.txt` contain multiple command outputs in one file.
The collector emits a marker line before each command's output:

```
### CMD: ip route ###
default via 192.168.1.1 dev eno1
...
### CMD: ss -tlnp ###
...
```

- Marker grammar: `### CMD: <verbatim command> ###` on its own line.
- A section runs from its marker to the next marker or end of file.
- The chunker splits exactly on these markers, one chunk per command section.
- There is no end marker.

Required commands in `system.txt`: `systemctl --failed`, `uptime`, `df -h`, `free -m`, `top -b -n 1 | head -30`.
Required commands in `network.txt`: `ip addr`, `ip route`, `ss -tlnp`, `cat /etc/resolv.conf`, `iptables -L -n` (or `nft list ruleset`).

## 5. Deposit protocol (transport -> inbox)

The Brain's inbox is `$BRAIN_INBOX` (default `~/brain/inbox/`).
Deposits must be atomic so the watcher never sees a half-copied bundle:

1. Copy the bundle into `$BRAIN_INBOX/.staging/bundle-<...>/`.
2. When the copy is complete, `mv` it to `$BRAIN_INBOX/bundle-<...>/` (atomic rename, same filesystem).

The watcher only considers directories at the inbox root whose names start with `bundle-`.
It ignores `.staging/` and any dotfile.

- SSH pull mode: `collector.sh` writes the bundle to `~/bundles/` on the client (override with `-o <dir>`); the operator runs `brain pull <host>` on the Brain, which fetches the newest `bundle-*` from that directory (manifest first, then the whole bundle) and performs both steps.
- scp push mode: the client scp's into `.staging/` and then runs `ssh brain mv ...` (the last two lines of `collector.sh`).
- USB mode: the operator runs `brain ingest /media/usb/bundle-<...>` on the Brain, which performs the two steps.

A bundle that fails validation (missing manifest, bad `contract_version`, oversize) is moved to `$BRAIN_INBOX/rejected/<bundle_id>/` with a `reject-reason.txt` beside it.
It is never silently dropped.

## 6. Chunk ID grammar (downstream, fixed here because reports cite it)

```
<machine_id>:<bundle-relative-path>:L<start>-L<end>
```

Example: `laptop-a:app_logs/backend.log:L120-L160`

- `machine_id` comes from the manifest.
- The path is relative to the bundle root, no leading slash.
- Line numbers are 1-based and inclusive.
- A whole-file chunk still carries its real line range (`L1-L42`).

This grammar is why section 1 and 2 forbid `:` in machine IDs and paths.

## 7. Versioning

- The Brain must reject bundles whose `contract_version` major version it does not know.
- Additive changes (new optional file, new manifest field) bump the minor version.
- Layout or grammar changes bump the major version.
