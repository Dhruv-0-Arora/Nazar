from conftest import ENV_CHUNK, LOG_CHUNK


def test_bm25_finds_the_symptom(case):
    retriever, _ = case
    hits = retriever.search("ENOTFOUND db connect failed", k=5)
    assert hits, "no hits at all"
    assert any(chunk.id == LOG_CHUNK for chunk, _ in hits)


def test_dangling_talks_to_edge_exists(case):
    """The money edge: backend's config points at a host no machine matches."""
    retriever, _ = case
    graph = retriever.graph
    dangling = [e for e in graph.edges.values() if e.rel == "talks_to" and e.attrs.get("dangling")]
    assert any(e.src == "service:laptop-a/backend" and e.dst == "host:db.internal" for e in dangling)


def test_cross_machine_talks_to_edge(case):
    retriever, _ = case
    graph = retriever.graph
    rels = {(e.src, e.rel, e.dst) for e in graph.edges.values()}
    assert ("service:laptop-b/frontend", "talks_to", "service:laptop-a/backend") in rels


def test_node_accumulates_evidence_across_machines(case):
    """port:5432 is mentioned by laptop-a's env file AND laptop-b's migration doc."""
    retriever, _ = case
    node = retriever.graph.nodes["port:5432"]
    machines = {cid.split(":", 1)[0] for cid in node.evidence}
    assert machines == {"laptop-a", "laptop-b"}


def test_expand_surfaces_the_config_chunk(case):
    """The demo claim: expanding from the log chunk reaches backend.env, which
    shares no vocabulary with 'connection failed' queries."""
    retriever, _ = case
    expansion = retriever.expand([LOG_CHUNK], hops=1)
    assert any(c.id == ENV_CHUNK for c in expansion.chunks)
    assert "DANGLING" in expansion.subgraph_text


def test_reasoning_caps_enforced(case):
    retriever, _ = case
    graph = retriever.graph
    results = [
        graph.apply_delta({"op": "add_node", "node": {"layer": "reasoning", "type": "hypothesis", "label": f"h{i}"}})
        for i in range(10)
    ]
    assert all("assigned_id" in r for r in results[:8])
    assert all("error" in r for r in results[8:])


def test_finding_requires_parent_and_stance(case):
    retriever, _ = case
    bad = retriever.graph.apply_delta({"op": "add_node", "node": {"layer": "reasoning", "type": "finding", "label": "orphan"}})
    assert "error" in bad
    unknown = retriever.graph.apply_delta({"op": "set_status", "id": "hyp:999", "status": "confirmed"})
    assert "error" in unknown
