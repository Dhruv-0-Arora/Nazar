# Runbook: fully linked interactive test

Two variants: everything on the GB10 (variant A, fastest), and the real two-machine setup with the MacBook as the client over the direct ethernet cable (variant B, the demo shape).
Both end the same way: the FDE Console in a browser at `http://localhost:8000/`, live against the Brain, diagnosing the clinic scenario.

Prerequisites (once): `cd brain && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`; `cd ui && npm install && VITE_USE_MOCK=false npm run build`; Ollama running with qwen3.5:122b.

## Variant A: single machine (GB10)

```bash
cd ~/Documents/whackathon

# 1. start the broken system locally
cd scenario && npm install && bash scripts/run-local.sh && bash scripts/inject.sh && cd ..
#    backend :8080 now failing, portal :3000 shows the symptom, services still "running"

# 2. start the Brain (serves API + FDE Console on :8000)
brain/.venv/bin/brain serve &

# 3. collect evidence into the inbox (local collection, so ingest directly)
./collector/collector.sh -o /tmp/bundles --services "clinic-backend clinic-portal" \
    --docs scenario/corpus --notes "portal shows records unavailable"
brain/.venv/bin/brain ingest /tmp/bundles/bundle-*

# 4. open http://localhost:8000/ (FDE Console, live by default)
#    type into the chat: "why is the patient portal failing?" - this starts the
#    diagnosis run; watch the trail, graph, and logs panels fill; the answer
#    arrives with chunk-id citations. Or from a terminal:
integration/openclaw/brainctl diagnose -q "why is the patient portal failing?"
integration/openclaw/brainctl watch <run_id>

# 5. reset when done
cd scenario && bash scripts/revert.sh && bash scripts/stop-local.sh 2>/dev/null; cd ..
```

Note for local (non-systemd) runs: the collector finds configs via `/etc/myapp`, `/etc/clinic`, and `/etc/<svc>/`; when running the scenario from the repo instead of a deployed host, point `EXTRA_PATHS` at the scenario's log files so they land in `app_logs/`:
`EXTRA_PATHS="$PWD/scenario/backend.log $PWD/scenario/frontend.log" ./collector/collector.sh ...` (check the actual log paths `run-local.sh` uses).

## Variant B: MacBook client over direct ethernet (the demo shape)

The MacBook is the "client server"; the GB10 is the Brain. Link-local IPv6 needs no DHCP/static config (see AIRGAP-SSH.md).

### B1. Bring up the link (GB10 side)

```bash
sudo nmcli device set enP7s7 managed no && sudo ip link set enP7s7 up
ping6 -c 2 -I enP7s7 ff02::1%enP7s7     # discover neighbors
ip -6 neigh show dev enP7s7             # note the Mac's fe80:: address
```

Add an SSH alias so ssh AND scp (and therefore `brain pull`) work without IPv6-literal quoting; `%%` is ssh_config's escape for a literal `%`:

```
# ~/.ssh/config
Host demo-mac
  HostName fe80::408:4412:3a20:c606%%enP7s7
  User dhruvarora
  BatchMode yes
```

Verify: `ssh demo-mac uptime`. If the address changed since last boot, rediscover (link-local IIDs are stable-ish, not guaranteed).

### B2. Deploy the scenario to the Mac

```bash
ssh demo-mac 'mkdir -p ~/clinic ~/bundles'
scp -r scenario demo-mac:~/clinic/
scp collector/collector.sh demo-mac:~/clinic/
ssh demo-mac 'node --version'    # needs Node; install if missing
```

On the Mac (no systemd there, so local mode):

```bash
ssh demo-mac 'cd ~/clinic/scenario && npm install && bash scripts/run-local.sh && bash scripts/inject.sh'
```

### B3. Collect on the Mac and pull to the Brain

```bash
ssh demo-mac 'cd ~/clinic && EXTRA_PATHS="$(ls ~/clinic/scenario/*.log 2>/dev/null | tr "\n" " ")" \
    bash collector.sh -o ~/bundles --services "clinic-backend clinic-portal" \
    --docs ~/clinic/scenario/corpus --notes "records portal down at the clinic site"'
brain/.venv/bin/brain pull demo-mac        # manifest first, then the bundle, atomic deposit
```

Caveat: collector.sh is Linux-first; on macOS the systemctl/journalctl/ip/ss sections degrade to `unavailable:` markers by design, and it has `wc -c` fallbacks for GNU `stat`, but macOS ships bash 3.2 - the first Mac run should be eyeballed (`ls ~/bundles`, check `manifest.json` parses). If it misbehaves, collect the same evidence with the usb-transport client instead (`transport-layer/usb-transport/client/setup.sh` + `collector.sh`, then `brainctl usb`).

### B4. Diagnose

```bash
brain/.venv/bin/brain serve &          # if not already running
# browser: http://localhost:8000/  -> chat: "why is the patient portal failing?"
# or: integration/openclaw/brainctl diagnose && brainctl watch <run_id>
```

The strongest live moment per SPEC: once the bundle is in the inbox, unplug the cable before pressing diagnose - retrieval runs entirely against local disk.

### B5. Reset

```bash
ssh demo-mac 'cd ~/clinic/scenario && bash scripts/revert.sh && bash scripts/stop-local.sh 2>/dev/null'
```

## Known gaps this test will surface (expected, tracked)

- The clinic scenario has never been diagnosed by the real model (ADR-0013); its distractors exist to make this harder. This runbook IS that verification - grade the first reports against `scenario/ground_truth.md` by hand.
- `eval/` still grades the retired Acme fixtures (ADR-0013 consequence); after a good clinic bundle exists, regenerate `brain/tests/fixtures/` from it and rewrite `eval/grading.py` criteria.
- collector.sh on macOS is unverified (see B3 caveat).
