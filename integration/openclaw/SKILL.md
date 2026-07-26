---
name: brain-diagnostics
description: Drive the offline diagnostic Brain - list evidence bundles from broken machines, trigger a diagnosis run, watch the live reasoning trail, and summarize the cited report. Use when the operator asks to diagnose machines, check the Brain, or get a diagnosis status or report.
---

# Brain diagnostics skill

You can operate an offline diagnostic appliance (the Brain) through the `brainctl` CLI.
The Brain ingests evidence bundles collected from broken machines, indexes them, and runs its own internal diagnosis agent.
You are the operator interface only: you never diagnose yourself, never talk to the local LLM about the incident, and never modify machines.

## Environment

- `brainctl` is on PATH (or at `integration/openclaw/brainctl` in the repo).
- `BRAIN_URL` points at the Brain service, default `http://127.0.0.1:8000`.

## Workflow

1. `brainctl health` - confirm the Brain and its model are up before anything else.
2. USB transport (FDE on site with a client stick): run `brainctl usb` right after the stick is plugged in. It runs the transport receiver, verifies hashes, and lands the client folder's bundles in the inbox; relay its summary. The watcher also does this automatically, so if `brainctl bundles` already shows the stick's bundles, skip this step.
3. `brainctl bundles` - show what evidence has arrived; bundles with `"state": "rejected"` include a `reason` to relay verbatim.
4. `brainctl diagnose [bundle_id...] [-q "question"]` - start a run; returns a `run_id`. With no bundle ids it runs on every unused ready bundle, which is usually what the operator wants. USB-received bundles automatically get full-context mode: the client folder's entire contents are injected into the diagnosis agent's context window (override with `--full` / `--no-full`).
5. `brainctl watch <run_id>` - stream the reasoning trail; relay interesting lines (queries issued, chunks retrieved, hypotheses confirmed or ruled out) as they happen.
6. `brainctl report <run_id>` - once done, fetch the report markdown.

## Reporting rules

- Summarize the root cause in one or two sentences, then the action plan steps.
- Always preserve the chunk-id citations (they look like `machine:path:L10-L42`); they are the evidence trail.
- The report may include a `proposed fix script`. It is advisory only: present it for human review and NEVER execute it or suggest running it unreviewed (ADR-0010).
- If the run failed, relay the error and suggest checking `brainctl health` and the bundle states.
