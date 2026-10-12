from app.retrieval.embedder import HashEmbedder
from app.retrieval.reranker import Reranker
from app.retrieval.retriever import Retriever
from tests.conftest import SAMPLE_DOCS, make_service


def _service_with_samples(**overrides):
    service = make_service(**overrides)
    service.ingest_directory(str(SAMPLE_DOCS))
    return service


def test_known_question_returns_the_expected_chunk():
    service = _service_with_samples()
    results = service.retriever.retrieve("How often must passwords be rotated?", k=5)

    assert results[0].chunk.doc_name == "security_handbook.md"
    assert "rotated every 180 days" in results[0].chunk.text
    assert [item.score for item in results] == sorted((item.score for item in results), reverse=True)


def test_pdf_chunks_keep_their_page_number():
    service = _service_with_samples()
    results = service.retriever.retrieve("expense claims submitted within 45 days", k=3)

    assert results[0].chunk.doc_name == "expense_policy.pdf"
    assert results[0].chunk.page == 2


def test_unrelated_question_scores_below_a_related_one():
    service = _service_with_samples()
    related = service.retriever.retrieve("How often must passwords be rotated?", k=1)[0].score
    unrelated = service.retriever.retrieve("Which country won the football world cup?", k=1)[0].score
    assert related > unrelated


def test_hybrid_adds_keyword_matches_and_still_reports_cosine_scores():
    service = _service_with_samples()
    embedder = HashEmbedder()
    hybrid = Retriever(service.store, embedder, hybrid=True, raw_k=4)

    results = hybrid.retrieve("Lumenfold-Guest network", k=10)

    ids = [item.chunk.chunk_id for item in results]
    assert len(ids) == len(set(ids)), "fusion must not return a chunk twice"
    assert any("Lumenfold-Guest" in item.chunk.text for item in results)
    expected = service.store.similarities(ids, embedder.embed_query("Lumenfold-Guest network"))
    for item in results:
        assert abs(item.score - expected[item.chunk.chunk_id]) < 1e-4


class _PreferB2(Reranker):
    def score(self, query: str, texts: list[str]) -> list[float]:
        return [1.0 if "Orbit B2" in text else 0.0 for text in texts]


def test_reranker_reorders_candidates():
    service = _service_with_samples()
    reranked = Retriever(service.store, HashEmbedder(), reranker=_PreferB2(), raw_k=12)

    results = reranked.retrieve("Orbit A1 battery life", k=3)

    assert "Orbit B2" in results[0].chunk.text
    assert len(results) == 3
