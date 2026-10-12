"""Internal data types passed between pipeline stages."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Page:
    number: int | None  # None for formats without pages (TXT, MD)
    text: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_name: str
    page: int | None
    index: int
    text: str


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float  # cosine similarity to the query, higher is closer


@dataclass
class RetrievalTrace:
    top_similarity: float = 0.0  # best first-pass similarity for the original question
    depth_reached: int = 0
    sub_questions: list[str] = field(default_factory=list)
    retrievals: int = 0
