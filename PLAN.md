M0 — Scenario Package (the broken system + its knowledge base)
The testbed and the fake corpus are authored together as one package, because the corpus must be tuned to the bug: one doc that's a near-miss (similar symptoms, wrong cause), one that genuinely helps, and a few noise docs. This is what forces the agent to reason instead of string-match.
Scenario SETUP on computer: we will have it ON a github repo: we will have a frontend + backend folder set in the github repo, backend will be the backend service that crashes (the crashing node app), the frontend will be the service that also breaks since requests stop working.
Scenario is installed on laptops via Github Repo, no need for complex scenario packaging we would just set it up on our servers that way.
BROKEN json syntax…
EDGE cases of parsing.
Empty env var
Firewall rule
Port in use
Assign a person to handle this whole thing: creating the backend and frontend issues is someones whole job
Write inject.sh: sets a wrong DB host env var in the backend service's config (e.g., edits /etc/myapp/backend.env), restarts the service. Idempotent — safe to run twice.
Could hypothetically make the bugs ourselves… sure
EASIER: URL or an endpoint in the environment variables is STALE, so server can’t communicate with frontend on another computer
Malformed input
Node app crashes


Write revert.sh: restores the correct env var, restarts service. Lets you re-run the demo cleanly.
Server should WRITE the revert.sh script and CREATE the fix
Stand up the mock system: minimal backend (Python/Flask or Node, one endpoint hitting a DB or mock DB) on laptop A; minimal frontend (static page or tiny app calling the backend) on laptop B.
Verify the bug's symptom chain: service reports "running" via systemctl, but requests fail and errors appear in the app log. This subtlety is the point.
Write the fake corpus (~10-20 short markdown docs) and place them in a known directory on the client (e.g., /opt/company-docs/): one near-miss past ticket ("2025-03: frontend 502s — root cause was firewall"), one relevant runbook ("backend DB connection settings live in backend.env"), several noise docs (unrelated tickets, generic runbooks).
GOOD: Company docs is a goodidea
Write ground_truth.md: the actual root cause and what a correct diagnosis must contain. Used for grading, never shipped to the client.
SURE
Write placement.json: which laptop gets the bug, which gets which corpus docs (put at least one useful doc on the other laptop to set up the cross-machine synthesis demo).
M2 — Client Collector (the "client app" layer)
One dependency-free bash script. Anything beyond bash breaks the "runs anywhere, fits on a USB stick" story.
So this part is the SET OF deterministic scripts that comes with our solution, its whole scope is to:
Have a setup (SUPER simple, just cli interface asking user what files on server they want to track, for example)
Must point to a LOG file
Then setup initiates COPYING of the working folder (with the problems, log files, etc) onto the USB stick.
The USB stick data, when put back onto the Brain, would then (with manual intervention) be able to be indexed into an artifact ON THE BRAIN
And them we use BM25 or Zoekt or graph search ON THAT ARTIFACT to then create some action plan, diagnose problems, etc.


SSH option is easy: simply put the brain can ssh into our laptops and scp the problem files, log files ETC as it pleases on its own. The working folder of problems and such would have a manifest in it that specifies file structures and such, and inform model on Brain to knwo what files to pull.
	All indexing and knowledge graphing is done on the brain.

Write collector.sh that creates bundle-<hostname>-<timestamp>/ and fills it with:
manifest.json — hostname, timestamp, OS version, collector version
system.txt — systemctl --failed, uptime, df -h, free -m, top snapshot
network.txt — ip addr, ip route, ss -tlnp, resolv.conf, iptables/nft rules
services/<name>/ — per-service: systemctl status, last 200 journal lines, copy of config files (this captures the buggy env file)
app_logs/ — tail of each application error log
processes.txt, packages.txt — ps aux, recent package changes
docs/ — copy of /opt/company-docs/ (the fake corpus rides along in the bundle)
Test it on a healthy laptop first, then on the bugged one; eyeball that the env var error is actually captured somewhere in the bundle.
Keep total bundle size small (truncate logs to last N lines) — target well under a few MB.
Here's a section you can drop in to replace/expand C1:

C1 — Transport
Connectivity: two modes, ranked
Primary — shared network. Brain and clients already on the same LAN; Brain SSHes over existing network. No cable, no static IPs, no setup step. Default path; demo runs on this unless forced otherwise.
Secondary — direct ethernet. Fallback when there's no shared network: infrastructure down, DHCP dead, client isolated. Point-to-point cable, static IPs, same SSH on top.
This is a connectivity choice, not an architecture choice. Identical scp/SSH transport against the identical bundle contract in both modes — only the IP the Brain dials changes. Nothing in collector.sh, CONTRACT.md, or the ingest path differs. Build and test on shared-network; the cable is a demo-day config change, not a code path.
Physical link (secondary mode only)
Ethernet is dumb transport — it carries frames, indifferent to whether they're an SSH session or an scp stream. Anything that works over a normal network works identically over a direct cable.
No crossover cable needed; auto-MDI-X standard on NICs for ~20 years.
No DHCP on a two-node link — assign static IPs beforehand (192.168.50.1 = Brain, .2/.3 = clients), or use IPv6 link-local, which comes up on its own.
/etc/hosts entries so scripts reference brain / client-a instead of hardcoded IPs.
1GbE ≈ 110 MB/s; bundles are capped at a few MB, so transfer is instant. Bandwidth is not a design constraint — the cable exists to prove zero infrastructure dependency, not for speed.
Worth making explicit in the pitch: the scenario premise is that the network is cooked, and a direct cable shows the Brain working with no DHCP, no DNS, no switch, no internet.
Transport modes, one contract
Mode
Initiator
Use
SSH/scp pull
Brain
Primary
scp push
Client (last line of collector.sh)
Fallback if Brain can't reach client

Both deposit an identical bundle directory into ~/brain/inbox/. The inbox watcher can't tell them apart — transport is swappable because CONTRACT.md fixes the interface.
Pull sequence
Brain scp's manifest.json from the client's bundle directory.
Brain reads it to learn structure and contents.
Brain pulls the full bundle (or, at larger sizes, only manifest-declared relevant paths).
For the hackathon, always pull whole in step 3 — selective fetch is a size optimization irrelevant at single-digit MB. The manifest is still required: it's what tells the model what it's looking at.
Where the work happens
All indexing, chunking, BM25, and graph construction run on the Brain, never on the client — the sick machine may be resource-starved or broken, and the Brain is the only box with the model. collector.sh stays dependency-free bash: collect and hand off.
Once a bundle lands in the inbox, transport is finished. Retrieval runs against local disk with no network round trips in the search loop, so the Brain can diagnose with the cable unplugged — a strong thing to show live.
Pre-demo checklist
Before the build window, not during it:
[ ] SSH keypairs exchanged both directions, passwordless login verified
[ ] ~/brain/inbox/ exists with correct permissions
[ ] One dry-run scp of a dummy bundle, end to end
[ ] (secondary mode only) Static IPs assigned and pinned, /etc/hosts populated

C2 — Data Contract
This is just the agreement about the bundle's directory layout above — but write it down, because it's the interface both people build against in parallel.
THIS ALSO combines with the process above, this has to do with how brain will KNOW the fiel structure of the problem folder, and as we said, that whole system will be setup in teh manifest linked into the folder with our problems.
Create CONTRACT.md in the repo listing the exact bundle structure, filenames, and formats (first 10 minutes of the build, both people sign off).
M3 developer immediately hand-crafts a fake bundle matching the contract so Brain work starts without waiting for M2.
THIS PART IS FULLY CLAUDE-ABLE
M3 — The Brain (inbox watcher + BM25 + agent loop + report)
Inbox watcher: Python script polling ~/brain/inbox/ for new bundle directories.
Ingest: read every text file in the bundle; chunk (per-file or ~500-token chunks for long logs); build a BM25 index (rank_bm25, ~20 lines) with filename metadata per chunk.
search(query, k) function — the single retrieval interface (the seam where embeddings swap in later).
Agent loop against qwen3.5:122b via Ollama:
Turn 1: model receives manifest + system.txt summary, asked to form hypotheses and emit search queries.
Turns 2-N: run queries through search(), feed back top-k chunks, model refines or concludes (cap at ~5 iterations).
Final turn: model emits structured output — root cause, evidence cited (filenames), next-steps action plan.
Report generator (markdown): diagnosis, action plan as a structured list (JSON alongside prose — this becomes the future autofix API), full query trail ("queries issued / chunks retrieved"), and elapsed wall-clock time in the header.
runs/ logging: every run saves the bundle copy, all queries, retrieved chunks, final report, elapsed time — your eval harness and future fine-tuning dataset for free.
Grade the output against ground_truth.md by eye; iterate the system prompt until diagnosis is reliably correct.


Why "chunk = node" is the wrong unification
The instinct to unify is right, but unifying at the object level conflates two different granularities:
A chunk is a span of evidence text — 40 lines of log, a config file, a runbook section. It's what BM25 scores and what you stuff into the model's context. Its defining property is that it's verbatim source material.
A node is a thing the text talks about — the machine laptopA, the service backend, the file backend.env, port 5432, the error class ECONNREFUSED, ticket #4412. Its defining property is that it's typed and connectable. The same node (port 5432) is mentioned by chunks scattered across three files on two machines — that many-to-many relationship is the entire value of the graph, and it's impossible if node and chunk are the same object.
And the reverse ordering (graph creates chunks, BM25 indexes the graph's output) has a worse flaw: chunking should be deterministic and stable (it's your retrieval substrate and your citation system), while entity/graph extraction is inherently fuzzy and iterative (regexes you'll tune, LLM passes you'll rerun). If chunk boundaries depend on graph logic, every graph tweak invalidates your inverted index and every chunk ID cited in prior reasoning. Decouple them and the graph can be rebuilt ten times per run while BM25 never re-indexes.
The architecture
One pipeline, three stages, at Brain ingest time:
bundles → [1. CHUNKER] → chunk store (id, text, metadata)
                │
                ├─→ [2. BM25]  inverted index: token → chunk_ids
                │
                └─→ [3. GRAPH BUILDER] nodes + edges,
                        every node carries evidence: [chunk_ids]
Chunk IDs are the universal currency: machine_id:file_path:span (e.g., laptopA:/app_logs/backend.log:L120-160). BM25 returns chunk IDs. Graph nodes point at chunk IDs. The report cites chunk IDs. The visual, when you click a node, displays its chunks. One ID scheme threads retrieval, reasoning, graph, and UI together — this is the unification you were actually after.
Stage 1 — Chunker (deterministic, structure-aware, per file type):
Logs: split on error-block boundaries (timestamp/severity lines) with a fallback of fixed ~40-line windows; store line-range in metadata
Configs (services/*/): whole file if small, else per stanza; tiny files are fine as single chunks
Corpus docs (docs/): split per markdown heading
Command outputs (system.txt, network.txt): one chunk per command section — contract change: have the collector emit delimiters (### CMD: ip route ###) so the chunker splits on markers instead of guessing
Every chunk gets metadata: {machine_id, hostname, file_path, span, kind: evidence|knowledge}
Stage 2 — BM25: unchanged from before, just formalized — tokenize chunks, inverted index token → chunk IDs, search(query, k) returns scored chunk IDs.
Stage 3 — Graph builder, two tiers, and this tiering is what keeps it MVP-feasible:
Structural tier (free, zero inference): nodes for Machine, Bundle, File, Service straight from the bundle layout and manifest; edges File—located_on→Machine, Service—has_config→File, Chunk—from→File. The directory structure is a graph already — just materialize it.
Extracted tier (regex, still deterministic): scan chunks for IPs, ports, hostnames, env-var keys, error classes (ECONNREFUSED, timeout, HTTP 5xx), ticket IDs → nodes with mentions edges back to their chunk IDs
The money edge: cross-reference extracted values — when a config chunk on laptopB contains an IP/port that belongs to laptopA's Machine node, emit Service—talks_to→Service. For scenario #1, this edge is the diagnosis made visible: frontend's config points at the backend, backend's env var points at a DB host that matches nothing in the graph — a dangling edge. A dangling talks_to edge is literally your bug rendered as topology.
Concept tier (LLM-extracted, optional): hypothesis/concept nodes the agent adds during reasoning. Cut from MVP unless time remains; the seam exists because adding nodes to networkx is trivial.
Store: networkx in memory; serialize nodes+edges to JSON per run (into runs/) — that JSON is what the visual layer (d3, or whatever you build) renders, and clicking a node resolves its evidence: [chunk_ids] against the chunk store
How the agent loop uses both
Retrieval becomes two complementary moves instead of one:
search(query) → top-k chunks (lexical entry point)
expand(chunk_ids) → follow chunks up to their nodes, traverse 1-2 hops, come back down to neighboring chunks the query never matched
That second move is what BM25 alone can't do: the agent searches "connection refused," lands in laptopA's log chunks, expands through the backend Service node, crosses the has_config edge, and surfaces the backend.env chunk — which never contains the words "connection refused" at all. Lexical search finds the symptom; the graph walks to the cause. That traversal, animated on screen, is your "hypotheses eliminated live" pitch moment rendered literally.
Build-order note: chunker first (Stage 2 and 3 both block on it), BM25 second (agent works end-to-end with search alone), graph third (pure upgrade, agent degrades gracefully without it if hour 3 arrives early).
One question back before you commit: for the visual, are you imagining the graph as a live reasoning display during diagnosis (nodes lighting up as the agent traverses), or as a post-hoc artifact in the report (static topology map with the dangling edge highlighted)? The JSON serialization serves both, but the live version needs a small websocket/refresh loop on the TUI side and is worth deciding now.
So the graph's generation of nodes would be based on the bundles, but it would make nodes independently... ? Like im confused here, what is the use of that then, the goal is to be able to go from:
user query --> to retreive results from graph (a SUBGRAPH) of relelvant info --> as well as relevant results from all the bundle files with BM25 --> syntehsize that information somehow.
Like are we executing another layer to be able to tie graph-generated nodes to chunks that are chunker-generated? Even though graph nodes are differnet from chunks?
Clarified simultaneous node-chunk linking during extraction, eliminating reconciliation needs
Clarified simultaneous node-chunk linking during extraction, eliminating reconciliation needs
No third layer — the tie is created at the moment of extraction, not reconciled afterward. That's the piece you're missing: nodes aren't made "independently," they're made by reading chunks, and every node records which chunks it was born from as it's created.
Where the link comes from
The graph builder's input IS the chunk store. It never sees the bundles directly:
python
for chunk in chunk_store:
    for match in extract_entities(chunk.text):     # regex: ports, IPs, env vars, error classes...
        node = graph.get_or_create(match.type, match.value)   # e.g. ("port", "5432")
        node.evidence.append(chunk.id)              # ← THE LINK. born here. no extra step.
        chunk.mentions.append(node.id)              # reverse direction, same instant
Two lines. When the regex finds "5432" inside chunk laptopA:/services/backend/backend.env:L1-12, the node port:5432 either gets created or already exists (because laptopB's config also mentioned it) — and either way this chunk ID is appended to its evidence list. The bidirectional mapping chunk ↔ nodes is a byproduct of extraction itself. There is nothing to tie together later; they were never separate.
This is also why the same node accumulates chunks from different machines. port:5432 ends up with evidence from laptopA's env file AND laptopB's nginx config AND laptopA's error log — three chunks, three files, two machines, one node. That accumulation is the whole point: the node is the junction where scattered mentions of the same real-world thing meet.
Your query flow, exactly as you wrote it, now mechanical
Query: "why is the frontend getting connection refused?"
BM25 → top-k chunks. Hits: laptopA's backend.log chunks containing ECONNREFUSED, maybe the near-miss ticket in docs/.
Chunks → subgraph. Take each hit chunk's mentions list → seed nodes (error:ECONNREFUSED, service:backend, port:5432, host:db.internal). Expand 1–2 hops along edges → the relevant subgraph. This is your "retrieve a SUBGRAPH" step — it's just: seed from BM25's chunks, expand neighbors.
Subgraph → more chunks. Every node in that subgraph carries its own evidence list — including chunks BM25 never scored, because they don't share vocabulary with the query. The backend.env chunk contains no words resembling "connection refused," but it's evidence on host:db.internal, which is one hop from the error node. It gets pulled in anyway.
Synthesize. The model's context = BM25's chunks + subgraph-surfaced chunks (deduped, each labeled with its chunk ID and the path that surfaced it: "via BM25" vs. "via graph: ECONNREFUSED → talks_to → db.internal → evidence"). Plus a compact text rendering of the subgraph itself (backend —talks_to→ db.internal [DANGLING: no machine matches]). The model reasons over symptoms, causes, and topology in one shot, and can cite chunk IDs for every claim.

FRONTEND:
Triaging/fde needs a frontend + graph visualizer to understand problems
Each node of the graph should have a code file


Why "chunk = node" is the wrong unification
The instinct to unify is right, but unifying at the object level conflates two different granularities:
A chunk is a span of evidence text — 40 lines of log, a config file, a runbook section. It's what BM25 scores and what you stuff into the model's context. Its defining property is that it's verbatim source material.
A node is a thing the text talks about — the machine laptopA, the service backend, the file backend.env, port 5432, the error class ECONNREFUSED, ticket #4412. Its defining property is that it's typed and connectable. The same node (port 5432) is mentioned by chunks scattered across three files on two machines — that many-to-many relationship is the entire value of the graph, and it's impossible if node and chunk are the same object.
And the reverse ordering (graph creates chunks, BM25 indexes the graph's output) has a worse flaw: chunking should be deterministic and stable (it's your retrieval substrate and your citation system), while entity/graph extraction is inherently fuzzy and iterative (regexes you'll tune, LLM passes you'll rerun). If chunk boundaries depend on graph logic, every graph tweak invalidates your inverted index and every chunk ID cited in prior reasoning. Decouple them and the graph can be rebuilt ten times per run while BM25 never re-indexes.
The architecture
One pipeline, three stages, at Brain ingest time:
bundles → [1. CHUNKER] → chunk store (id, text, metadata)
                │
                ├─→ [2. BM25]  inverted index: token → chunk_ids
                │
                └─→ [3. GRAPH BUILDER] nodes + edges,
                        every node carries evidence: [chunk_ids]
Chunk IDs are the universal currency: machine_id:file_path:span (e.g., laptopA:/app_logs/backend.log:L120-160). BM25 returns chunk IDs. Graph nodes point at chunk IDs. The report cites chunk IDs. The visual, when you click a node, displays its chunks. One ID scheme threads retrieval, reasoning, graph, and UI together — this is the unification you were actually after.
Stage 1 — Chunker (deterministic, structure-aware, per file type):
Logs: split on error-block boundaries (timestamp/severity lines) with a fallback of fixed ~40-line windows; store line-range in metadata
Configs (services/*/): whole file if small, else per stanza; tiny files are fine as single chunks
Corpus docs (docs/): split per markdown heading
Command outputs (system.txt, network.txt): one chunk per command section — contract change: have the collector emit delimiters (### CMD: ip route ###) so the chunker splits on markers instead of guessing
Every chunk gets metadata: {machine_id, hostname, file_path, span, kind: evidence|knowledge}
Stage 2 — BM25: unchanged from before, just formalized — tokenize chunks, inverted index token → chunk IDs, search(query, k) returns scored chunk IDs.
Stage 3 — Graph builder, two tiers, and this tiering is what keeps it MVP-feasible:
Structural tier (free, zero inference): nodes for Machine, Bundle, File, Service straight from the bundle layout and manifest; edges File—located_on→Machine, Service—has_config→File, Chunk—from→File. The directory structure is a graph already — just materialize it.
Extracted tier (regex, still deterministic): scan chunks for IPs, ports, hostnames, env-var keys, error classes (ECONNREFUSED, timeout, HTTP 5xx), ticket IDs → nodes with mentions edges back to their chunk IDs
The money edge: cross-reference extracted values — when a config chunk on laptopB contains an IP/port that belongs to laptopA's Machine node, emit Service—talks_to→Service. For scenario #1, this edge is the diagnosis made visible: frontend's config points at the backend, backend's env var points at a DB host that matches nothing in the graph — a dangling edge. A dangling talks_to edge is literally your bug rendered as topology.
Concept tier (LLM-extracted, optional): hypothesis/concept nodes the agent adds during reasoning. Cut from MVP unless time remains; the seam exists because adding nodes to networkx is trivial.
Store: networkx in memory; serialize nodes+edges to JSON per run (into runs/) — that JSON is what the visual layer (d3, or whatever you build) renders, and clicking a node resolves its evidence: [chunk_ids] against the chunk store
How the agent loop uses both
Retrieval becomes two complementary moves instead of one:
search(query) → top-k chunks (lexical entry point)
expand(chunk_ids) → follow chunks up to their nodes, traverse 1-2 hops, come back down to neighboring chunks the query never matched
That second move is what BM25 alone can't do: the agent searches "connection refused," lands in laptopA's log chunks, expands through the backend Service node, crosses the has_config edge, and surfaces the backend.env chunk — which never contains the words "connection refused" at all. Lexical search finds the symptom; the graph walks to the cause. That traversal, animated on screen, is your "hypotheses eliminated live" pitch moment rendered literally.
Build-order note: chunker first (Stage 2 and 3 both block on it), BM25 second (agent works end-to-end with search alone), graph third (pure upgrade, agent degrades gracefully without it if hour 3 arrives early).
One question back before you commit: for the visual, are you imagining the graph as a live reasoning display during diagnosis (nodes lighting up as the agent traverses), or as a post-hoc artifact in the report (static topology map with the dangling edge highlighted)? The JSON serialization serves both, but the live version needs a small websocket/refresh loop on the TUI side and is worth deciding now.
So the graph's generation of nodes would be based on the bundles, but it would make nodes independently... ? Like im confused here, what is the use of that then, the goal is to be able to go from:
user query --> to retreive results from graph (a SUBGRAPH) of relelvant info --> as well as relevant results from all the bundle files with BM25 --> syntehsize that information somehow.
Like are we executing another layer to be able to tie graph-generated nodes to chunks that are chunker-generated? Even though graph nodes are differnet from chunks?
Clarified simultaneous node-chunk linking during extraction, eliminating reconciliation needs
Clarified simultaneous node-chunk linking during extraction, eliminating reconciliation needs
No third layer — the tie is created at the moment of extraction, not reconciled afterward. That's the piece you're missing: nodes aren't made "independently," they're made by reading chunks, and every node records which chunks it was born from as it's created.
Where the link comes from
The graph builder's input IS the chunk store. It never sees the bundles directly:
python
for chunk in chunk_store:
    for match in extract_entities(chunk.text):     # regex: ports, IPs, env vars, error classes...
        node = graph.get_or_create(match.type, match.value)   # e.g. ("port", "5432")
        node.evidence.append(chunk.id)              # ← THE LINK. born here. no extra step.
        chunk.mentions.append(node.id)              # reverse direction, same instant
Two lines. When the regex finds "5432" inside chunk laptopA:/services/backend/backend.env:L1-12, the node port:5432 either gets created or already exists (because laptopB's config also mentioned it) — and either way this chunk ID is appended to its evidence list. The bidirectional mapping chunk ↔ nodes is a byproduct of extraction itself. There is nothing to tie together later; they were never separate.
This is also why the same node accumulates chunks from different machines. port:5432 ends up with evidence from laptopA's env file AND laptopB's nginx config AND laptopA's error log — three chunks, three files, two machines, one node. That accumulation is the whole point: the node is the junction where scattered mentions of the same real-world thing meet.
Your query flow, exactly as you wrote it, now mechanical
Query: "why is the frontend getting connection refused?"
BM25 → top-k chunks. Hits: laptopA's backend.log chunks containing ECONNREFUSED, maybe the near-miss ticket in docs/.
Chunks → subgraph. Take each hit chunk's mentions list → seed nodes (error:ECONNREFUSED, service:backend, port:5432, host:db.internal). Expand 1–2 hops along edges → the relevant subgraph. This is your "retrieve a SUBGRAPH" step — it's just: seed from BM25's chunks, expand neighbors.
Subgraph → more chunks. Every node in that subgraph carries its own evidence list — including chunks BM25 never scored, because they don't share vocabulary with the query. The backend.env chunk contains no words resembling "connection refused," but it's evidence on host:db.internal, which is one hop from the error node. It gets pulled in anyway.
Synthesize. The model's context = BM25's chunks + subgraph-surfaced chunks (deduped, each labeled with its chunk ID and the path that surfaced it: "via BM25" vs. "via graph: ECONNREFUSED → talks_to → db.internal → evidence"). Plus a compact text rendering of the subgraph itself (backend —talks_to→ db.internal [DANGLING: no machine matches]). The model reasons over symptoms, causes, and topology in one shot, and can cite chunk IDs for every claim.

FRONTEND:
Triaging/fde needs a frontend + graph visualizer to understand problems
Each node of the graph should have a code file
M3.5 — Concurrency
Two axes worth building:
Across bundles. Inbox watcher dispatches each bundle to a worker; runs are fully independent (own index, own loop, own runs/ entry). Bound by semaphore = OLLAMA_NUM_PARALLEL.
Fan-out within a turn. Issue all N hypothesis queries concurrently, feed back in one turn. BM25 is CPU-bound and cheap; each turn removed is a full decode cycle saved.
The agent loop itself is serial — turn N+1 depends on turn N. Don't parallelize it.
Ollama config: OLLAMA_NUM_PARALLEL=2, OLLAMA_MAX_LOADED_MODELS=1. At 2 slots expect ~35–40 tok/s each, ~75 aggregate. Weights are shared; each slot needs its own KV cache. If VRAM won't fit 2, set 1 and queue — predictable serial latency beats swapping mid-demo.
Budget at 50 tok/s: terse-JSON intermediate turns (~50 tok ≈ 1s) + one 800-token report ≈ 20s/run. Verify thinking mode is off for intermediate turns or that number silently triples. Log eval_count / eval_duration from every Ollama response into runs/ so this is measured, not assumed.
Prefix cache: the message array is append-only. Never mutate earlier turns and keep anything variable (timestamps) out of the system prompt — breaking the cache costs seconds per turn and raises no error.
M4 — Brain Service
All diagnosis logic is Python: Ollama client, BM25 index, agent loop, graph CLI, behind one FastAPI layer. Everything that touches the model goes through llm.py — the swap seam for vLLM or llama.cpp later, same as search() is the seam for embeddings. The frontend never calls Ollama directly: it would have to reimplement the agent loop, has no access to search() or the bundle, and gets no run state or query trail.
POST /runs                    trigger a run on a bundle → run_id
GET  /runs                    list runs, status, elapsed
GET  /runs/{id}               full report (JSON + prose)
GET  /runs/{id}/stream        SSE: tokens, queries, chunks, graph deltas
GET  /runs/{id}/graph         nodes + edges for the visualizer
GET  /runs/{id}/chunks/{cid}  raw chunk, for click-through from a node
This API contract is the frontend/backend seam, exactly as CONTRACT.md is the collector/Brain seam. Write it in the first 10 minutes; frontend then builds against mocked JSON, unblocked.
M4.1 — Frontend & Graph
Stack. React + sigma.js (WebGL). Served as a static build by the Python server, so there's one process and one port.
Incremental mutation, not regeneration. The model never emits the whole graph. It calls a CLI that appends single operations against persistent state:
graph add-node   --type {hypothesis|evidence|cause} --label ... --source <file> --chunk <cid>
graph add-edge   --from <id> --to <id> --rel {retrieved_by|supports|contradicts}
graph set-status --id <id> --status {open|confirmed|ruled_out}
Each call returns the new node ID and nothing else — keeps tokens out of the loop. CLI writes to the graph store; API emits the delta over the SSE stream; sigma.js patches in place without full relayout.
Caps. Hard limit ~150 nodes, enforced in the CLI, not the prompt — the model cannot exceed it. Per-run caps: ~8 hypotheses, ~5 evidence nodes each. On overflow, evict lowest-BM25-score evidence on ruled-out branches. Node labels ≤80 chars; full text lives behind GET /runs/{id}/chunks/{cid} on click. Each node carries its source filename and chunk ID, so clicking opens the actual file from the bundle.
M4.2 — Live Run View
Chain: Ollama stream: true → NDJSON → llm.py re-emits → FastAPI SSE → EventSource in React. One connection, no polling, multiplexed event types:
event: token       {"turn": 2, "text": "..."}
event: query       {"q": "backend.env DB host", "k": 5}
event: chunk       {"cid": "...", "file": "services/backend/config", "score": 8.1}
event: graph       {"op": "add-node", "id": "n7", ...}
event: status      {"turn": 3, "state": "refining"}
event: done        {"run_id": "...", "elapsed": 19.4}
Lead the UI with the query trail, not the token stream. Intermediate turns are terse JSON, so a raw firehose shows ~3s of {"queries":[...]} then a 16s wall of report text. Render query/chunk events as a live trail instead — "Hypothesis: stale DB host → searching → retrieved backend.env (8.1)" — and reserve token streaming for the final turn. The trail is the most convincing part of the demo: it shows reasoning rather than asserting it.
Three gotchas: flush the token buffer on requestAnimationFrame, not per token, or setState thrashes at 50 tok/s × 2 runs. EventSource auto-reconnects and replays from the top — stamp events with a sequence number and dedupe client-side. If thinking mode is on for the final turn, tag reasoning tokens as a separate event type and collapse them by default.


