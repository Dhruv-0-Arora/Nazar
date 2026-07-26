from brain.ingest.bundle import load_manifest
from brain.ingest.chunker import chunk_bundle
from conftest import BUNDLE_A, ENV_CHUNK, LOG_CHUNK


def chunks_for(bundle):
    manifest = load_manifest(bundle)
    return chunk_bundle(bundle, manifest)


def test_cmd_sections_split_on_markers():
    chunks = [c for c in chunks_for(BUNDLE_A) if c.file_path == "network.txt"]
    firsts = [c.text.splitlines()[0] for c in chunks]
    assert len(chunks) == 5
    assert all(f.startswith("### CMD: ") for f in firsts)
    assert any("ss -tlnp" in f for f in firsts)


def test_log_and_config_chunk_ids_match_grammar():
    ids = {c.id for c in chunks_for(BUNDLE_A)}
    assert LOG_CHUNK in ids
    assert ENV_CHUNK in ids


def test_docs_are_knowledge_everything_else_evidence():
    chunks = chunks_for(BUNDLE_A)
    for c in chunks:
        expected = "knowledge" if c.file_path.startswith("docs/") else "evidence"
        assert c.kind == expected, c.id


def test_markdown_splits_on_headings():
    chunks = [c for c in chunks_for(BUNDLE_A) if c.file_path == "docs/runbook-backend-config.md"]
    assert len(chunks) == 3  # H1, Keys, Applying changes
    assert chunks[1].text.startswith("## Keys")


def test_spans_are_one_based_inclusive():
    for c in chunks_for(BUNDLE_A):
        start, end = c.span
        assert 1 <= start <= end
        assert c.id.endswith(f"L{start}-L{end}")


def test_chunking_is_deterministic():
    a = [(c.id, c.text) for c in chunks_for(BUNDLE_A)]
    b = [(c.id, c.text) for c in chunks_for(BUNDLE_A)]
    assert a == b
