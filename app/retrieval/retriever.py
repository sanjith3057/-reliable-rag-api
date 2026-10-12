"""Retrieval: dense by default, optional BM25 fusion and reranking, and recursive multi-hop on top."""

from collections.abc import Callable

from app.domain import RetrievalTrace, ScoredChunk
from app.retrieval.bm25 import BM25Index
from app.retrieval.embedder import Embedder
from app.retrieval.reranker import Reranker
from app.retrieval.vector_store import VectorStore


class Retriever:
    """Returns chunks in ranking order. `score` is always cosine similarity, whatever did the ranking,
    so the abstention gate means the same thing with every retrieval configuration."""

    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        *,
        hybrid: bool = False,
        reranker: Reranker | None = None,
        raw_k: int = 12,
        dense_weight: float = 0.65,
        bm25_weight: float = 0.35,
    ):
        self.store = store
        self.embedder = embedder
        self.hybrid = hybrid
        self.reranker = reranker
        self.raw_k = raw_k
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight
        self._bm25: BM25Index | None = None
        self._bm25_version = -1

    def retrieve(self, query: str, k: int) -> list[ScoredChunk]:
        embedding = self.embedder.embed_query(query)
        widen = self.hybrid or self.reranker is not None
        candidates = self.store.query(embedding, max(k, self.raw_k) if widen else k)
        if self.hybrid:
            candidates = self._fuse_with_bm25(query, embedding, candidates)
        if self.reranker is not None and candidates:
            scores = self.reranker.score(query, [item.chunk.text for item in candidates])
            order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
            candidates = [candidates[i] for i in order]
        return candidates[:k]

    def with_neighbours(self, query: str, chunks: list[ScoredChunk], limit: int) -> list[ScoredChunk]:
        """Add the chunks that sit next to the retrieved ones in their document, up to `limit` in total.

        A list or a section is often longer than one chunk, and search may return its first and last
        part but not the middle. Chunks between two retrieved ones are added first, then the chunk
        after each hit, then the chunk before it.
        """
        room = limit - len(chunks)
        if room <= 0 or not chunks:
            return chunks
        seen = {(item.chunk.doc_id, item.chunk.index) for item in chunks}
        wanted: list[str] = []

        def want(doc_id: str, index: int) -> None:
            if index >= 0 and (doc_id, index) not in seen:
                seen.add((doc_id, index))
                wanted.append(f"{doc_id}:{index}")  # the chunk id format set by the chunker

        positions: dict[str, list[int]] = {}
        for item in chunks:
            positions.setdefault(item.chunk.doc_id, []).append(item.chunk.index)
        for doc_id, indexes in positions.items():
            indexes.sort()
            for first, second in zip(indexes, indexes[1:], strict=False):
                if second - first <= 3:
                    for index in range(first + 1, second):
                        want(doc_id, index)
        for step in (1, -1):
            for item in chunks:
                want(item.chunk.doc_id, item.chunk.index + step)

        found = {chunk.chunk_id: chunk for chunk in self.store.get_chunks(wanted)}
        extra = [found[chunk_id] for chunk_id in wanted if chunk_id in found][:room]
        if not extra:
            return chunks
        similarities = self.store.similarities([chunk.chunk_id for chunk in extra], self.embedder.embed_query(query))
        return chunks + [ScoredChunk(chunk=chunk, score=similarities.get(chunk.chunk_id, 0.0)) for chunk in extra]

    def _fuse_with_bm25(self, query: str, embedding: list[float], dense: list[ScoredChunk]) -> list[ScoredChunk]:
        """Weighted reciprocal-rank fusion: each list contributes weight / rank."""
        keyword_hits = self._bm25_index().search(query, self.raw_k)
        by_id = {item.chunk.chunk_id: item for item in dense}
        fused: dict[str, float] = {}
        for rank, item in enumerate(dense, start=1):
            fused[item.chunk.chunk_id] = self.dense_weight / rank
        for rank, chunk in enumerate(keyword_hits, start=1):
            fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + self.bm25_weight / rank

        keyword_only = [chunk for chunk in keyword_hits if chunk.chunk_id not in by_id]
        similarities = self.store.similarities([chunk.chunk_id for chunk in keyword_only], embedding)
        for chunk in keyword_only:
            by_id[chunk.chunk_id] = ScoredChunk(chunk=chunk, score=similarities.get(chunk.chunk_id, 0.0))
        return [by_id[chunk_id] for chunk_id in sorted(fused, key=lambda cid: fused[cid], reverse=True)]

    def _bm25_index(self) -> BM25Index:
        if self._bm25 is None or self._bm25_version != self.store.version:
            self._bm25 = BM25Index(self.store.all_chunks())
            self._bm25_version = self.store.version
        return self._bm25


def dedupe(chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """Keep each chunk once, with its best score, strongest first."""
    best: dict[str, ScoredChunk] = {}
    for item in chunks:
        current = best.get(item.chunk.chunk_id)
        if current is None or item.score > current.score:
            best[item.chunk.chunk_id] = item
    return sorted(best.values(), key=lambda item: item.score, reverse=True)


class RecursiveRetriever:
    """Multi-hop retrieval that only spends an LLM call when first-pass evidence is middling.

    - top similarity >= sufficiency: evidence is good, stop.
    - top similarity <  gate:        nothing relevant, stop (the caller will abstain).
    - in between:                    ask `decompose` for sub-questions and retrieve each, up to max_depth.
    """

    def __init__(
        self,
        retriever: Retriever,
        decompose: Callable[[str], list[str]],
        *,
        gate: float,
        sufficiency: float,
        max_depth: int = 2,
        max_sub_questions: int = 3,
    ):
        self.retriever = retriever
        self.decompose = decompose
        self.gate = gate
        self.sufficiency = sufficiency
        self.max_depth = max_depth
        self.max_sub_questions = max_sub_questions

    def retrieve(self, question: str, k: int) -> tuple[list[ScoredChunk], RetrievalTrace]:
        trace = RetrievalTrace()
        chunks = self._recurse(question, k, 0, trace)
        return chunks, trace

    def _recurse(self, question: str, k: int, depth: int, trace: RetrievalTrace) -> list[ScoredChunk]:
        chunks = self.retriever.retrieve(question, k)
        trace.retrievals += 1
        trace.depth_reached = max(trace.depth_reached, depth)
        top = max((item.score for item in chunks), default=0.0)
        if depth == 0:
            trace.top_similarity = top
        if top >= self.sufficiency or top < self.gate or depth >= self.max_depth:
            return chunks

        sub_questions = [q for q in self.decompose(question) if q.strip()][: self.max_sub_questions]
        if not sub_questions:
            return chunks
        trace.sub_questions.extend(sub_questions)
        results = list(chunks)
        for sub_question in sub_questions:
            results += self._recurse(sub_question, k, depth + 1, trace)
        return dedupe(results)
