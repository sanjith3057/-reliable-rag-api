"""Pick the few sentences of a cited chunk that actually carry the evidence.

Done locally with the embedder (no extra LLM call): sentences are ranked by similarity
to the question plus the answer, and the best ones are returned in document order.
"""

import re

from app.retrieval.embedder import Embedder, cosine

_MIN_SENTENCE_CHARS = 20


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip(" \t-*#|") for part in parts if part.strip(" \t-*#|")]


def best_excerpt(text: str, query: str, embedder: Embedder, max_sentences: int = 3, max_chars: int = 400) -> str:
    sentences = split_sentences(text)
    # Headings and list labels have no closing punctuation; they are not evidence on their own.
    candidates = [s for s in sentences if len(s) >= _MIN_SENTENCE_CHARS and s[-1] in ".!?"] or sentences
    if not candidates:
        return text.strip()[:max_chars]
    if len(candidates) == 1:
        return candidates[0][:max_chars]

    query_vector = embedder.embed_query(query)
    scores = [cosine(vector, query_vector) for vector in embedder.embed_documents(candidates)]
    ranked = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)

    # Always keep the best sentence; add runners-up only if they are nearly as relevant.
    best_score = scores[ranked[0]]
    chosen = [ranked[0]]
    for index in ranked[1:max_sentences]:
        if scores[index] >= 0.85 * best_score and scores[index] > 0:
            chosen.append(index)

    excerpt = " … ".join(candidates[i] for i in sorted(chosen))
    return excerpt[:max_chars].rstrip()
