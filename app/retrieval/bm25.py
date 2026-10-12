"""Optional keyword index for hybrid retrieval. Built in memory from the chunks in the vector store."""

import re

from app.domain import Chunk


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        from rank_bm25 import BM25Okapi  # lazy: only loaded when hybrid search is switched on

        self._chunks = chunks
        self._bm25 = BM25Okapi([tokenize(chunk.text) for chunk in chunks]) if chunks else None

    def search(self, query: str, k: int) -> list[Chunk]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [self._chunks[i] for i in ranked if scores[i] > 0]
