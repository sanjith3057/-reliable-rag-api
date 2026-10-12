"""ChromaDB wrapper. The only place that knows Chroma returns distances, not similarities."""

from datetime import UTC, datetime

from app.domain import Chunk, ScoredChunk
from app.retrieval.embedder import cosine

_NO_PAGE = 0  # Chroma metadata cannot hold None


def distance_to_similarity(distance: float) -> float:
    """Chroma's cosine space reports distance = 1 - cosine similarity.

    A smaller distance means a closer match, so comparing a raw distance against a
    "minimum similarity" threshold would invert the abstention gate. Convert here, once.
    """
    return 1.0 - distance


class VectorStore:
    def __init__(self, path: str, collection_name: str):
        import chromadb  # lazy: about a second to import, only needed once a store is opened

        self._client = chromadb.PersistentClient(path=path) if path else chromadb.EphemeralClient()
        self._name = collection_name
        self._collection = self._open()
        self.version = 0  # bumped on every write so derived indexes know to rebuild

    def _open(self):
        return self._client.get_or_create_collection(self._name, metadata={"hnsw:space": "cosine"})

    def count(self) -> int:
        return self._collection.count()

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        ingested_at = datetime.now(UTC).isoformat(timespec="seconds")
        self._collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            embeddings=embeddings,
            metadatas=[
                {
                    "doc_id": chunk.doc_id,
                    "doc_name": chunk.doc_name,
                    "page": chunk.page or _NO_PAGE,
                    "chunk_index": chunk.index,
                    "ingested_at": ingested_at,
                }
                for chunk in chunks
            ],
        )
        self.version += 1

    def query(self, embedding: list[float], k: int) -> list[ScoredChunk]:
        total = self.count()
        if total == 0:
            return []
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(k, total),
            include=["documents", "metadatas", "distances"],
        )
        return [
            ScoredChunk(chunk=_to_chunk(chunk_id, text, meta), score=distance_to_similarity(distance))
            for chunk_id, text, meta, distance in zip(
                result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
            )
        ]

    def similarities(self, chunk_ids: list[str], embedding: list[float]) -> dict[str, float]:
        """Cosine similarity of stored chunks to a query vector, for chunks found by a non-vector route."""
        if not chunk_ids:
            return {}
        result = self._collection.get(ids=chunk_ids, include=["embeddings"])
        return {
            chunk_id: cosine([float(x) for x in vector], embedding)
            for chunk_id, vector in zip(result["ids"], result["embeddings"], strict=True)
        }

    def all_chunks(self) -> list[Chunk]:
        result = self._collection.get(include=["documents", "metadatas"])
        return [
            _to_chunk(chunk_id, text, meta)
            for chunk_id, text, meta in zip(result["ids"], result["documents"], result["metadatas"], strict=True)
        ]

    def list_documents(self) -> list[dict]:
        result = self._collection.get(include=["metadatas"])
        documents: dict[str, dict] = {}
        for meta in result["metadatas"]:
            entry = documents.setdefault(
                meta["doc_id"],
                {
                    "doc_id": meta["doc_id"],
                    "doc_name": meta["doc_name"],
                    "chunks": 0,
                    "pages": 0,
                    "ingested_at": meta.get("ingested_at", ""),
                },
            )
            entry["chunks"] += 1
            entry["pages"] = max(entry["pages"], meta["page"])
        return sorted(documents.values(), key=lambda doc: doc["doc_name"].lower())

    def delete_document(self, doc_id: str) -> int:
        existing = self._collection.get(where={"doc_id": doc_id}, include=[])
        if not existing["ids"]:
            return 0
        self._collection.delete(ids=existing["ids"])
        self.version += 1
        return len(existing["ids"])

    def reset(self) -> int:
        removed = self.count()
        self._client.delete_collection(self._name)
        self._collection = self._open()
        self.version += 1
        return removed


def _to_chunk(chunk_id: str, text: str, meta: dict) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=meta["doc_id"],
        doc_name=meta["doc_name"],
        page=meta["page"] or None,
        index=meta["chunk_index"],
        text=text,
    )
