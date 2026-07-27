![NazarLogo](https://drive.google.com/uc?export=view&id=1mCaD1XI4S2j5CjTBKV3Wy9SDB3IEZuXe)

**An offline AI that figures out why a computer system broke, without ever touching the internet.**

You wheel a box into a hospital, a factory, or a ship.
It reads the broken machines, thinks about it, and tells you what went wrong and how to fix it.
No cloud, no data leaving the building.

> 🥈 **2nd place** out of 40 teams at the [Dell x NVIDIA Hackathon](https://luma.com/aiu9lo9y), *Local AI on Dell Pro Max with GB10*.
> Seattle, July 2026. Built in one day, on the box it runs on.

## Watch the demo

[![Nazar demo video](https://img.youtube.com/vi/nNunx93hYl4/maxresdefault.jpg)](https://www.youtube.com/watch?v=nNunx93hYl4)

*Click the image to play on YouTube.*

## The problem

When something breaks in a normal company, an engineer opens a laptop, googles the error, and pastes logs into ChatGPT.

Now imagine you can't do any of that.
The site is a clinic with patient records that legally cannot leave the building.
Or a submarine.
Or a bank running a vault network that has no internet by design.

These places still break, and the person sent to fix them is usually alone, on site, under time pressure, staring at a machine they've never seen before.
That person is called a Forward Deployed Engineer, and their job is mostly detective work: read the logs, read the configs, remember the one runbook that mentioned this, and connect the dots.

Nazar is that detective, in a box.

## The hardest part: it looks fine

The bugs Nazar hunts are the ones that make everything *look* healthy.

Every fault in our test scenario obeys one rule: **the service stays "running" and the health check stays green.**
A crash is easy - anyone finds a crash in ten seconds.
The expensive outages are the ones where every dashboard is green, every process is alive, and the thing simply does not work.

Example: a config file points the app at a database server that was decommissioned last year.
The app starts fine. The health check passes, because it never actually calls the database.
Only real user requests fail.
That's the kind of thing that eats an hour of a war room's time, and it's what Nazar is built to catch.

## How it works

Four steps, in plain English.

**1. Collect.**
A single shell script runs on the broken machine and packs up everything useful into a folder: logs, config files, running processes, network state, plus whatever internal documentation lives on that machine.
It's dependency-free bash on purpose, because the sick machine might not have Python, internet, or much of anything.

**2. Carry.**
That folder gets to the Nazar box however it can.
Over the network if there is one, over a plain ethernet cable strung between the two machines, or on a USB stick if the network itself is the thing that's broken.
All three routes drop off an identical package, so nothing downstream knows or cares how it arrived.

The cable route is the one worth seeing: Nazar watches the port, and **plugging the cable in is the entire user interaction.**
It notices the link come up, finds the machine on the other end, pulls the evidence, and starts diagnosing. Nobody types anything.

**3. Understand.**
Nazar chops everything into small labelled pieces, makes them searchable, and builds a map of how things connect: which service talks to which database, which config file belongs to which service, which machine hosts what.

That map is where the magic is.
Text search finds you the *symptom* ("connection refused").
The map walks you from the symptom to the *cause*, which is often in a file that shares zero words with your search.
It also spots the smoking gun directly: when a config points at a machine that doesn't exist anywhere in the evidence, that dangling connection gets flagged. The bug, drawn as a picture.

**4. Diagnose.**
A large language model running locally on the box works the case like a detective, in rounds.
It searches, reads what comes back, writes down hypotheses, walks the map, rules things in and out, and repeats.
When it's done it writes a report: what broke, why, the evidence for it, and the steps to fix it.

Every claim in the report is a footnote pointing at a real line in a real file from the real machine.
Click it and you see the source.
No trusting the AI, just check its work.

Meanwhile the screen shows all of this happening live - the thinking, the searches, the map growing and rearranging itself.

## What it will not do

Nazar writes the fix. It never runs it.

A machine that can diagnose is a machine that could also break things worse, and an offline box with nobody watching is exactly where you don't want that.
A human reads the plan and pushes the button.

## The tech, briefly

| Piece | What it is |
|---|---|
| **Brain** | Python 3.12 + FastAPI. Does the ingesting, searching, mapping, and reasoning. |
| **Model** | `qwen3.5:122b` running locally through Ollama. Plus a small embedding model that tidies the map. |
| **Hardware** | A Dell Pro Max with GB10, 120 GB of unified memory. The whole thing is two processes. |
| **Search** | BM25 keyword search over the chunks, plus graph traversal for the leaps keyword search can't make. |
| **Map** | A `networkx` graph in two layers: hard evidence pulled from the files, and the AI's own reasoning drawn on top. |
| **UI** | React + `@xyflow/react` + zustand + Tailwind, built with Vite. Streams live over SSE. |
| **Collector** | ~430 lines of portable bash. No dependencies, by design. |

A few design rules the whole codebase follows:

- **Every piece of evidence has a permanent ID** shaped `machine:path:Lstart-Lend`. Search results, map nodes, report footnotes, and UI clicks all speak that one language. There is no second ID scheme anywhere.
- **Chunking is deterministic.** The map can be thrown away and rebuilt as often as you like; the evidence IDs never move.
- **Limits live in code, not in prompts.** Map size, label length, number of thinking rounds. You don't ask a language model nicely to stay in bounds.
- **The two seams are contracts.** `CONTRACT.md` (collector to Brain) and `API.md` (Brain to UI) only change with a version bump and sign-off from both sides.

## The test patient

Diagnosing something is only impressive if the answer wasn't obvious, so we built a system specifically designed to be misleading.

`scenario/` is Cedar Hollow Community Health, a fake clinic's patient records portal.
Three services across two laptops: a backend, a mock database, and a web portal.
All the patient data is fabricated. No real person is in there.

It ships with six different ways to break it, a difficulty ladder from "single file, single machine" up to faults that need cross-machine reasoning to catch.

Alongside it sits a knowledge base of 13 hand-written documents, and here's the nasty bit: they're **split across the two laptops so that the document explaining the fault lives on the opposite machine from the fault itself.**
You physically cannot solve it from one machine's evidence.
The knowledge base also contains a runbook that genuinely cracks the case, an old support ticket that looks relevant and isn't, and a pile of noise.

Then there are the **red herrings**, which are the part to point a skeptic at.
There's a log line on a timer that says "connection pool saturated."
There's a config file full of legacy keys nothing reads.
And there's `backend/pool.js`, a complete connection-pool implementation containing three real, genuinely findable bugs - an off-by-one, a race condition, and a leaked timer - that is *dead code*, gated behind a feature flag that is never true.

Every one of these is also present in the **healthy** bundle, so none of them correlate with the outage.
Diagnosing any of them is scored as a total failure, not partial credit.
This is the thing that separates a real diagnosis from a language model producing a confident, well-cited, wrong paragraph.

The answer key lives in `scenario/ground_truth.md` and never ships to a client machine.
`eval/run_eval.py` runs N trials through the real model and auto-grades each report against 13 criteria - 8 required, 5 bonus - so "it works" is a number rather than a vibe.
One of those criteria is inverted: blaming the firewall is an automatic zero.

## Try it

You'll need a Linux box with Ollama and a big model pulled, but the pieces run independently.

```bash
# The Brain
cd brain
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest          # test suite
.venv/bin/brain serve               # starts on :8000

# The UI (builds into the Brain's static mount)
cd ui
npm install && VITE_USE_MOCK=false npm run build

# The broken clinic, all three services locally
cd scenario
npm install && bash scripts/run-local.sh

# Break it, then collect the evidence
ENV_FILE=.local/backend.env bash scripts/inject.sh
./collector/collector.sh -o ~/bundles --services "clinic-backend clinic-portal"

# Heal it again
ENV_FILE=.local/backend.env bash scripts/revert.sh
```

Then open `http://localhost:8000` and watch it work.

**No GPU? Most of it still runs.**
The UI works standalone against built-in fixtures (`npm run dev`), so you can click around the console with nothing behind it.
The Python test suite needs no model either: it ships a fake LLM that implements the exact same seam, plus two complete example bundles, so the entire pipeline is exercised offline.
The clinic itself has zero runtime dependencies - it's Node standard library only, on purpose, because the whole point is running on machines where you can't `npm install` anything.

## Where things live

```
brain/         the Python service: ingest, search, graph, agent loop, API
ui/            the React console (this is "Nazar" proper)
collector/     the one bash script that runs on broken machines
scenario/      the deliberately broken clinic + its knowledge base
transport-layer/  USB stick tooling for when the network is the casualty
integration/   brainctl CLI + operator chat layer
eval/          the grading harness
```

## Reading the docs

- `SPEC.md` - the architecture, in full detail. Source of truth.
- `CONTRACT.md` - what a bundle looks like going from a broken machine to the Brain.
- `API.md` - the HTTP and streaming schemas between the Brain and the UI.
- `AIRGAP-SSH.md` - how to talk to a machine over nothing but a cable.
- `scenario/BREAKAGE.md` - the fault catalogue and the difficulty ladder.

---

Built in a day at the Dell x NVIDIA hackathon in Seattle.
Named after the *nazar*, the blue eye amulet people hang up to catch trouble before it reaches them.
