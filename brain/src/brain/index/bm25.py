"""Lexical retrieval: rank_bm25 wrapper (SPEC section 6.2).

Compound tokens like db.internal, ECONNREFUSED, 192.168.50.10:5432 survive
whole AND as fragments, so both exact and partial queries land.
"""

import re

from rank_bm25 import BM25Okapi

from ..ingest.chunker import Chunk

TOKEN_RE = re.compile(r"[a-z0-9_.:\-/]+")
FRAGMENT_RE = re.compile(r"[^a-z0-9]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_RE.findall(text.lower()):
        raw = raw.strip(".:-/_")
        if not raw:
            continue
        tokens.append(raw)
        for frag in FRAGMENT_RE.split(raw):
            if frag and frag != raw:
                tokens.append(frag)
    return tokens


class Bm25Index:
    def __init__(self, chunks: list[Chunk]):
        self._ids = [c.id for c in chunks]
        corpus = [tokenize(c.text) or ["-"] for c in chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        """Top-k (chunk_id, score), positive scores only."""
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self._ids, scores), key=lambda p: p[1], reverse=True)
        return [(cid, float(s)) for cid, s in ranked[:k] if s > 0]
