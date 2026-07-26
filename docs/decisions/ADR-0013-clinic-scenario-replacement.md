# ADR-0013: Replace the Acme inventory scenario with the clinic scenario

Status: accepted.
Supersedes the scenario package described in ADR-0002.

## Context

The original `scenario/` was an Acme inventory system: a 132-line Node backend on port 3001, a 19-line TCP banner mock-db, a frontend on 8080, paths under `/opt/myapp`, and a 12-doc corpus.
It was end-to-end verified and had a good grading key.

A second scenario was built in parallel: a Cedar Hollow clinic patient records portal.
It is larger (roughly 2,100 lines against 580) and carries four capabilities the original did not have.

Keeping both was rejected: two scenarios in one repo invites confusion about which is authoritative, and they cannot run at once because the original frontend port is the clinic backend port.

## Decision

The clinic scenario replaces the Acme scenario at `scenario/`.

What the replacement adds:

- **Inert distractors.** `backend/pool.js` is a connection pool with three genuine defects that is dead code behind `FEATURE_ASYNC_RECORDS=false`. `backend/maintenance.js` emits four advisory warnings on a timer. `backend.env` carries five unread keys including `DB_HOST_LEGACY`. Every distractor is inert and appears in a healthy bundle as well as a faulted one, so none of them correlate with the outage. The original had exactly one distractor, the near-miss corpus ticket.
- **Hint enforcement.** `scripts/nuke.sh` strips a deployed copy of tooling, internal docs, backups, and comments carrying internal language, rewrites the README as plain operations documentation, then verifies the strip and confirms the fault survived. The original relied on `install.sh` not copying `ground_truth.md`, which is a convention rather than an enforced and verified property.
- **Built-artifact deployment.** `scripts/build.sh` emits minified bundles; `scripts/deploy.sh` stages a prod host holding artifact and config but no source, separately from a build host holding source but no config. The original copied raw source to `/opt/myapp`.
- **Fault variants.** Four scripted faults plus two wired but unscripted, ranked by reasoning difficulty in `BREAKAGE.md`. The original had one.

What was rebuilt to avoid regression, since the clinic package did not originally have it:

- 13-doc corpus with `placement.json`, keeping the disjoint per-laptop design and the cross-machine synthesis doc on the opposite machine from the fault.
- `ground_truth.md` with grading bands, extended with a fail trap per distractor.
- systemd units and `install.sh` for the two-laptop deployment.

## Consequences

- **Ports and paths changed.** Backend 3001 to 8080, frontend 8080 to portal 3000, `/opt/myapp` to `/opt/clinic`, `/etc/myapp` to `/etc/clinic`.
- **Brain source is unaffected.** The scenario strings in `retrieval.py`, `graph/build.py`, and `index/bm25.py` are docstring and comment examples, not logic.
- **Brain tests are unaffected.** They run against static fixtures under `brain/tests/fixtures/`, not against a live scenario.
- **Stale examples remain.** `SPEC.md`, `CLAUDE.md`, and `collector/README.md` reference the old ports and paths in illustrative text. Not load-bearing, but they should be refreshed.
- **The fixtures now describe a system that no longer exists.** They still exercise the chunker, retrieval, and graph correctly, but a future fixture refresh should regenerate them from a real clinic bundle.
- **The eval harness is now measuring a retired scenario, and this is the most important consequence.** `eval/run_eval.py` grades against `brain/tests/fixtures/`, not against `scenario/`, so nothing breaks and the pass rate stays meaningful for what it measures. But what it measures is the Acme case: `eval/grading.py` requires `db.internal` in the root cause and treats the firewall ticket as the only trap. It will keep reporting a healthy pass rate while telling you nothing about whether the agent can solve the scenario that will actually be demoed. `grading.py` was deliberately left untouched, because retargeting it at the clinic strings while the fixtures still contain Acme content would fail every trial and be strictly worse. Closing this properly means regenerating both fixture bundles from a real clinic collection, then rewriting the criteria: `db-primary.cedarhollow.internal` for the stale host, and one trap criterion per distractor in `scenario/ground_truth.md` rather than the single firewall check.
- **The end-to-end verification is invalidated.** The previous package was verified against a real model run. This one has not been, and the distractors are specifically designed to make diagnosis harder. Re-run the end-to-end check before relying on it, and measure whether the agent still reaches the correct root cause with the distractors present.

## Alternative considered

Porting the four capabilities into the Acme scenario and keeping it as the base.
That preserved the verified end-to-end run and avoided rewriting the corpus, ground truth, and deployment.
It was rejected in favour of the larger and more realistic clinic implementation.
