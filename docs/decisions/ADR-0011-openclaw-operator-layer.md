# ADR-0011: OpenClaw is the operator layer; OpenShell deferred to the autofix phase

Status: accepted (per Dhruv's requirement that one of openclaw / openshell / nemoclaw be part of the project).

## Context

One of the three must be implemented.
They are related layers of the same ecosystem, not three alternatives at the same altitude:

- OpenClaw: open-source agent orchestration / personal-assistant gateway (Node). Already installed on the Brain.
- OpenShell: NVIDIA's policy-enforced sandbox runtime that governs what an agent can see, do, and where its inference goes; ships with Nemotron integration and audit logging.
- NemoClaw: NVIDIA's enterprise stack that wraps OpenClaw with OpenShell, Nemotron models, and privacy routing.

## Decision

OpenClaw is the operator-facing control layer for the Brain, integrated exclusively through the existing Brain API (API.md), packaged as an OpenClaw skill in `integration/openclaw/`.

- The skill teaches the OpenClaw agent to drive the Brain with a small CLI wrapper (`brainctl`): list bundles, trigger a diagnosis run, watch progress, and fetch/summarize the report.
- The Brain's own agent loop stays purpose-built Python (SPEC.md section 7); OpenClaw never reimplements it and never talks to Ollama about diagnosis directly. This preserves the M4 rule that everything touching the model goes through `llm.py` and everything touching a run goes through the API.
- NemoClaw (the full stack) is out of scope: it is an enterprise packaging of the other two and far too heavy for the hackathon.
- OpenShell is deferred, not rejected: it becomes relevant exactly when the Brain graduates from proposing fixes to applying them (the `action_plan` autofix path from ADR-0010). Running fix execution inside an OpenShell policy sandbox with audit logging is the right shape for that phase, and is noted in ground truth for the pitch ("here is how this becomes enterprise-deployable").

## Rationale

- Best integration for what this project actually does today: the Brain diagnoses and never executes, so OpenShell's governance layer would wrap an agent that takes no governable actions; the integration cost buys nothing demoable in the MVP.
- OpenClaw is already installed, runs on the already-installed Node, and plugs into the API seam with zero changes to the Brain's architecture; it also gives the demo a second entry point (chat with the Brain) alongside the UI.
- The layering story stays honest for the pitch: OpenClaw today, OpenShell when autofix lands, NemoClaw as the enterprise path.

## Consequences

- New top-level directory `integration/openclaw/` (skill definition + `brainctl`); SPEC.md section 15 specifies it.
- The Brain API is now consumed by two clients (UI and OpenClaw), which it was designed for; API.md gains no new endpoints.
- OPEN-QUESTIONS item 3 (role of openclaw) is resolved and removed.
