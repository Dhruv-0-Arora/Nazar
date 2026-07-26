# Open Questions

Items where PLAN.md is ambiguous, silent, or contradictory and a human decision is needed.
When one is settled, record it as an ADR in `docs/decisions/` and delete it from here.
Items already decided unilaterally (with rationale) are in the ADRs; this list is only what still needs discussion.

## 1. Primary demo bug

PLAN lists many candidates: broken JSON syntax, JSON parsing edge cases, empty env var, firewall rule, port in use, stale URL/endpoint, malformed input, wrong DB host.
The spec assumes the primary is the wrong/stale DB host env var (it is the one `inject.sh` is specified around, and the one the dangling `talks_to` edge renders beautifully).
Proposal: wrong DB host is the demo bug; one or two others (port in use, firewall rule) are prepared as backup scenarios if time allows, each with its own inject/revert pair and ground truth.
Needs: scenario owner sign-off.

## 2. "Each node of the graph should have a code file"

PLAN's frontend section says this twice, verbatim, and it is ambiguous.
The spec interprets it as: clicking a node opens its evidence chunks, i.e. the actual file content from the bundle (API.md chunk endpoint).
Alternative reading: every node type has its own source/renderer file in the UI codebase.
Needs: confirmation of which was meant.

## 3. OLLAMA_NUM_PARALLEL: 1 or 2

PLAN M3.5 budgets for 2 parallel slots (~35-40 tok/s each).
qwen3.5:122b is 81 GB on a 120 GB unified-memory box; a second KV cache plus the OS plus qwen3-embedding:8b is unverified headroom.
The spec defaults to 1 and requires measuring before raising to 2 (SPEC.md section 9).
Needs: a 30-minute measurement on the GB10 (load model, run two concurrent generations, watch memory and tok/s), then pin the value.

## 4. Thinking mode on the final turn

PLAN M3.5 warns the 20 s/run budget "silently triples" if thinking is on for intermediate turns; the spec disables it there.
For the conclude turn, thinking may substantially improve diagnosis quality at the cost of wall-clock and a collapsed-by-default UI section.
Needs: an eval pass both ways on the fixture bundle, then a default.

## 5. Corpus duplication across bundles

`placement.json` splits docs across laptops, but if both machines copy all of `/opt/company-docs/`, the same doc can arrive in two bundles and produce near-duplicate chunks (skewing BM25 and cluttering citations).
Options: (a) placement guarantees disjoint doc sets per machine, (b) ingest dedupes `docs/` chunks by content hash across a case.
Proposal: (a) for MVP since we control placement, with (b) noted as hardening.
Needs: scenario owner sign-off.

## 6. Auto-run vs manual trigger for the live demo

ADR-0006 supports both (debounce auto-run, manual button).
For the stage demo, manual is safer (press when both bundles are visibly in); auto is more impressive ("it just noticed").
Needs: a rehearsal-time call; the code supports both either way.

## 7. Bundle copies in runs/

SPEC stores a verbatim copy of each case's bundles in `runs/<run_id>/bundles/` for reproducibility (PLAN M3: "every run saves the bundle copy").
If disk churn on the Brain becomes a concern with many runs, switch to hard-links or references.
Low stakes; default stands unless someone objects.

