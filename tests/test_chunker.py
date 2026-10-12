import pytest

from app.domain import Page
from app.ingestion.chunker import chunk_pages, split_text

LONG_TEXT = "\n\n".join(
    f"Paragraph {n}. " + " ".join(f"Sentence {n}-{i} carries a little bit of content." for i in range(12))
    for n in range(8)
)


def test_chunks_respect_the_size_limit():
    chunks = split_text(LONG_TEXT, chunk_size=800, overlap=120)
    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 800 for chunk in chunks)


def test_consecutive_chunks_overlap():
    chunks = split_text(LONG_TEXT, chunk_size=400, overlap=120)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        first_sentence = current.split(". ")[0]
        assert first_sentence in previous, "each chunk should start with the tail of the one before"


def test_no_text_is_lost():
    chunks = split_text(LONG_TEXT, chunk_size=400, overlap=0)
    assert "".join(chunks).replace(" ", "").replace("\n", "") == LONG_TEXT.replace(" ", "").replace("\n", "")


def test_short_text_is_one_chunk():
    assert split_text("Just one short sentence.") == ["Just one short sentence."]


def test_one_very_long_token_is_cut_hard():
    chunks = split_text("x" * 2000, chunk_size=800, overlap=100)
    assert all(len(chunk) <= 800 for chunk in chunks)
    assert "".join(chunks) == "x" * 2000


def test_empty_text_gives_no_chunks():
    assert split_text("   \n\n  ") == []


def test_invalid_sizes_are_rejected():
    with pytest.raises(ValueError):
        split_text("text", chunk_size=100, overlap=100)


def test_chunk_metadata_is_present():
    pages = [Page(number=1, text=LONG_TEXT), Page(number=2, text="Second page text.")]
    chunks = chunk_pages(pages, doc_id="abc123", doc_name="handbook.pdf", chunk_size=800, overlap=120)

    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert all(chunk.doc_id == "abc123" and chunk.doc_name == "handbook.pdf" for chunk in chunks)
    assert chunks[0].page == 1
    assert chunks[-1].page == 2 and chunks[-1].text == "Second page text."
