"""Embedders. The real one is a local sentence-transformers model; the hash one keeps tests offline."""

import math
import re
import zlib
from abc import ABC, abstractmethod

# bge models are trained with this prefix on the query side only.
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_STOPWORDS = frozenset(
    "a an and are as at be by do does for from how in is it its of on or that the this to was what "
    "when where which who why will with".split()
)


class Embedder(ABC):
    name: str

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str):
        self.name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import, deferred

            self._model = SentenceTransformer(self.name)
        return self._model

    def warm_up(self) -> None:
        self._load()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._load().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

    def embed_query(self, text: str) -> list[float]:
        prefix = _BGE_QUERY_PREFIX if "bge" in self.name.lower() else ""
        return self._load().encode([prefix + text], normalize_embeddings=True, show_progress_bar=False)[0].tolist()


class HashEmbedder(Embedder):
    """Deterministic bag-of-words vectors. No model download, so tests and CI run anywhere.

    It only captures word overlap, which is enough to test the plumbing around retrieval.
    """

    name = "hash-bow"

    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            if token not in _STOPWORDS:
                vector[zlib.crc32(token.encode()) % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def build_embedder(provider: str, model_name: str) -> Embedder:
    if provider == "hash":
        return HashEmbedder()
    return SentenceTransformerEmbedder(model_name)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
