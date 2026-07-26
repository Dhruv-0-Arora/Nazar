# ADR-0012: USB intake adapter + full-context injection for FDE-on-site runs

Status: accepted.

## Context

The `transport-layer/usb-transport/` package (Berkan) added a second collector family: an interactive `setup.sh`/`setup.ps1` writing `collect.conf`, collectors for Linux and Windows that bundle FDE-chosen problem folders and logs into `client/outbox/` on the stick, and `workstation/receive_bundle.py` which verifies sha256/sizes and copies bundles to the Brain inbox.
Its bundles speak a dialect of the contract: `contract_version "1"`, uppercase hostnames in bundle names (`bundle-BK608-...`), a different manifest schema (`created_at_utc`, `targets`, per-file `kind`/`sha256`), no `machine_id`, and no `processes.txt`; they also carry arbitrary `problem/` trees.
Unmodified, every one of them would be rejected by CONTRACT v1.0 validation.
Separately, Dhruv requires that (a) the agent can automatically run `receive_bundle.py` to pull everything from the client folder, and (b) USB-transported cases inject the client folder's full contents into the agent's context window.

## Decision

1. Reuse, do not reimplement: the Brain wraps `receive_bundle.py` (preferring the copy shipped on the stick itself) rather than duplicating its verification. `brain/src/brain/ingest/usb.py` discovers client outboxes (USB mount globs, `BRAIN_USB_SOURCES`, the repo copy), runs the receiver into `inbox/.staging/usb/`, and only then takes over.
2. Normalize at the boundary: each receiver-verified bundle is adapted to CONTRACT v1.0 before deposit - lowercased/sanitized `machine_id` and bundle name, a contract manifest synthesized from the USB dialect (original kept as `manifest.usb.json`), missing required files synthesized with an `unavailable` marker - then validated and atomically renamed into the inbox. Everything downstream (watcher, chunker, graph, UI) sees one contract.
3. Three triggers, one path: the watcher auto-scans for plugged-in sticks each poll (`BRAIN_USB_WATCH`), `POST /api/usb/receive` serves the UI and tooling, and `brainctl usb` serves the FDE and the OpenClaw agent. All converge on `usb.receive()`.
4. Full-context mode: a run whose bundles carry a `receipt.json` with `transport: "usb"` defaults to injecting every chunk verbatim into the first user message, delimited by chunk IDs so the citation system and click-through keep working. Evidence chunks outrank knowledge chunks under a char budget (`BRAIN_FULL_CTX_CHARS`, default 300k); omissions are announced to the model with instructions to retrieve the rest. Explicit `full_context: true|false` on `POST /api/runs` (or `brainctl diagnose --full/--no-full`) overrides the default. `search()`/`expand()` remain available in the loop unchanged.
5. `llm.py` now pins `options.num_ctx` (`BRAIN_NUM_CTX`, default 32768) on every Ollama call: without it, injected context silently overflows Ollama's default window, which truncates exactly the evidence the mode exists to provide.

## Rationale

- The FDE-on-site story is different from the appliance story: the operator is standing at the machine, chose the problem folders personally, and wants the model to see everything immediately; retrieval-first is tuned for corpora larger than a context window, which a curated USB client folder usually is not.
- Injecting chunks (not raw files) keeps one citation currency (ADR-0004) - reports from full-context runs cite the same `machine:path:Lx-Ly` IDs the UI resolves.
- Normalizing at the receiver keeps the CONTRACT invariant that the watcher cannot tell transports apart (ADR-0003), instead of teaching every downstream stage two manifest dialects.

## Consequences

- Prompt-eval cost rises with bundle size in full-context mode; the budget cap and `num_ctx` bound it. The prefix cache still applies within a run (the dump sits in the immutable first user message).
- Two collector families now coexist (`collector/` for SSH-mode Linux clients, `transport-layer/.../client/` for FDE sticks incl. Windows). Converging them on one manifest schema (v1.1 with sha256) is the natural next contract change, negotiated with the transport owner.
- OPEN-QUESTIONS #7 (interactive vs fixed capture set) is resolved by reality: the SSH collector stays fixed-set, the USB client is interactive by design.
