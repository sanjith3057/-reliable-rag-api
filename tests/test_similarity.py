"""Guards the bug that silently breaks grounding: treating Chroma's distance as a similarity."""

import uuid

import pytest

from app.domain import Chunk
from app.retrieval.vector_store import VectorStore, distance_to_similarity


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(chunk_id=chunk_id, doc_id="d", doc_name="d.txt", page=None, index=0, text=text)


def test_distance_converts_to_similarity():
    assert distance_to_similarity(0.0) == 1.0  # identical vectors
    assert distance_to_similarity(0.25) == 0.75
    assert distance_to_similarity(1.0) == 0.0  # orthogonal vectors


def test_smaller_distance_means_higher_similarity():
    assert distance_to_similarity(0.1) > distance_to_similarity(0.9)


def test_store_scores_a_close_match_above_a_far_match():
    store = VectorStore(path="", collection_name=f"sim-{uuid.uuid4().hex}")
    store.add(
        [_chunk("same", "same direction"), _chunk("near", "nearby"), _chunk("far", "orthogonal")],
        [[1.0, 0.0, 0.0], [0.8, 0.6, 0.0], [0.0, 0.0, 1.0]],
    )

    results = store.query([1.0, 0.0, 0.0], k=3)
    scores = {item.chunk.chunk_id: item.score for item in results}

    assert scores["same"] == pytest.approx(1.0, abs=1e-5)
    assert scores["near"] == pytest.approx(0.8, abs=1e-5)  # the true cosine similarity, not 0.2
    assert scores["far"] == pytest.approx(0.0, abs=1e-5)
    assert [item.chunk.chunk_id for item in results] == ["same", "near", "far"]


def test_empty_store_returns_nothing():
    store = VectorStore(path="", collection_name=f"sim-{uuid.uuid4().hex}")
    assert store.query([1.0, 0.0, 0.0], k=5) == []
