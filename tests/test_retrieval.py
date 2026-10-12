from app.domain import ScoredChunk
from app.generation.prompt import is_overview_question
from app.generation.providers import FakeLLM
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


# ── Neighbouring chunks ──────────────────────────────────────────────────────
def _long_document_service():
    service = make_service()
    text = "\n\n".join(f"Section {i}. " + f"Topic {i} is described here in some detail. " * 14 for i in range(8))
    service.ingest("long.txt", text.encode())
    chunks = sorted(service.store.all_chunks(), key=lambda chunk: chunk.index)
    assert len(chunks) >= 7
    return service, chunks


def test_chunks_between_two_hits_are_added_first():
    service, chunks = _long_document_service()
    hits = [ScoredChunk(chunks[1], 0.9), ScoredChunk(chunks[4], 0.8)]

    result = service.retriever.with_neighbours("topic", hits, limit=4)

    assert [item.chunk.index for item in result] == [1, 4, 2, 3], "the hits keep their place; the gap is filled"
    assert all(0.0 <= item.score <= 1.0 for item in result)


def test_neighbours_follow_each_hit_and_respect_the_limit():
    service, chunks = _long_document_service()
    hits = [ScoredChunk(chunks[0], 0.9), ScoredChunk(chunks[5], 0.8)]

    assert [c.chunk.index for c in service.retriever.with_neighbours("topic", hits, limit=5)] == [0, 5, 1, 6, 4]
    assert service.retriever.with_neighbours("topic", hits, limit=2) == hits, "no room, nothing added"


def test_the_whole_section_reaches_the_model():
    llm = FakeLLM()
    service = make_service(llm, top_k=1, max_context_chunks=3)
    text = "\n\n".join(f"Section {i}. " + f"Topic {i} is described here in some detail. " * 14 for i in range(8))
    service.ingest("long.txt", text.encode())

    service.ask("Topic 3 is described here in some detail.")

    assert llm.calls[-1][1].count("<source id=") == 3, "one hit plus its two neighbours"


def test_the_gap_between_the_two_best_hits_is_filled_first():
    service, chunks = _long_document_service()
    # Best first: 3 and 6 are the top two; 1 is the weakest. Room for two more chunks only.
    hits = [ScoredChunk(chunks[3], 0.9), ScoredChunk(chunks[6], 0.8), ScoredChunk(chunks[1], 0.5)]

    result = service.retriever.with_neighbours("topic", hits, limit=5)

    assert [item.chunk.index for item in result] == [3, 6, 1, 4, 5]


# ── Whole-document questions ─────────────────────────────────────────────────
def test_overview_questions_are_recognised():
    for question in ["Summarise this document", "Give me a summary", "What is this document about?", "key points?"]:
        assert is_overview_question(question), question
    for question in ["How often must passwords be rotated?", "What is the refund window?"]:
        assert not is_overview_question(question), question
    long_question = "In the summary table on page four, what is the figure given for the third quarter of 2025?"
    assert not is_overview_question(long_question), "a long, specific question is searched as usual"


def test_a_summary_question_reads_across_the_document_and_skips_the_gate():
    llm = FakeLLM()
    # A gate this high would refuse every searched question.
    service = make_service(llm, similarity_threshold=0.99, overview_chunks=4)
    text = "\n\n".join(f"Section {i}. " + f"Topic {i} is described here in some detail. " * 14 for i in range(8))
    service.ingest("long.txt", text.encode())

    outcome = service.ask("Summarise this document")

    assert outcome.response.answerable is True
    prompt = llm.calls[-1][1]
    assert "sampled from across the whole library" in prompt
    assert "Section 0." in prompt and "Section 7." in prompt, "the start and the end are both in the context"
    assert service.ask("Topic 3?").response.abstain_reason == "below_threshold", "other questions still meet the gate"
