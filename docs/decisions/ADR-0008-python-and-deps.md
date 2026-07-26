# ADR-0008: Python 3.12, BM25 via rank_bm25, embeddings behind a seam

Status: accepted.

## Context

The plan asked which Python version to install, and floated "BM25 or Zoekt or graph search" for retrieval.
The Brain (GB10) already has Python 3.12.3, Node, Ollama with qwen3.5:122b (81 GB) and qwen3-embedding:8b.

## Decision

- Python 3.12 (already installed; nothing new to install). Pinned as `requires-python = ">=3.12,<3.13"` in `brain/pyproject.toml`.
- Dependencies: fastapi, uvicorn, rank_bm25, networkx, httpx, sse-starlette, pydantic. All pure-Python or wheel-safe on 3.12. Standard venv + pip; no build system exotica.
- Lexical retrieval is rank_bm25 (BM25Okapi), not Zoekt: Zoekt is a Go server tuned for code trigram search; running and shelling out to it buys nothing over ~20 lines of rank_bm25 at our corpus size (a few MB).
- `retrieval.search(query, k)` is the single retrieval seam. qwen3-embedding:8b (already pulled) can swap in behind it later as a hybrid scorer without touching the agent loop, exactly as `llm.py` is the seam for replacing Ollama.

## Rationale

- 3.12 is the most battle-tested release for this dependency set; nothing in the project needs 3.13/3.14 features, and hackathon time should not be spent on toolchain risk.
- Every heavyweight capability (LLM, embeddings) sits behind Ollama's HTTP API, so the Python side stays pure and trivially installable.

## Consequences

- Clients need no Python at all; collector.sh is bash + coreutils only.
- If retrieval quality disappoints, the upgrade path is hybrid BM25 + embedding rerank behind `search()`, not a retrieval rewrite.
