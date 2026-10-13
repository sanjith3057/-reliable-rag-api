"""Scanned PDFs: pages without a text layer are read with OCR, within a page limit."""

import io

import pytest

from app.errors import AppError
from app.ingestion.loaders import load_document
from app.ingestion.ocr import OcrUnavailable, lines_in_reading_order, ocr_pdf_pages, page_confidence
from app.ingestion.vision import drop_repeated_tail
from tests.conftest import SAMPLE_DOCS, assert_error, make_client, make_service, upload

LIMIT = 10_000_000


def scanned_pdf(*page_texts: str) -> bytes:
    """A PDF whose pages are pictures of text, like the output of a scanner."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default(size=44)
    images = []
    for text in page_texts:
        image = Image.new("RGB", (1240, 600), "white")
        ImageDraw.Draw(image).multiline_text((60, 60), text, fill="black", font=font, spacing=24)
        images.append(image)
    buffer = io.BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def fake_ocr(data: bytes, page_numbers: list[int]) -> dict[int, str]:
    return {number: f"Recognised text of page {number}." for number in page_numbers}


def test_a_scanned_pdf_has_no_text_without_ocr():
    with pytest.raises(AppError) as error:
        load_document("scan.pdf", scanned_pdf("Invoice total 4200"), LIMIT)
    assert error.value.code == "NO_TEXT_EXTRACTED"


def test_scanned_pages_are_read_with_ocr():
    pages = load_document("scan.pdf", scanned_pdf("one", "two"), LIMIT, ocr=fake_ocr)

    assert [(page.number, page.text, page.from_ocr) for page in pages] == [
        (1, "Recognised text of page 1.", True),
        (2, "Recognised text of page 2.", True),
    ]


def test_typed_pages_never_reach_ocr():
    def must_not_run(data, page_numbers):
        raise AssertionError("OCR was called for a PDF that already has text")

    typed = next(SAMPLE_DOCS.glob("*.pdf"), None)
    if typed is None:
        pytest.skip("no typed PDF among the sample documents")
    pages = load_document(typed.name, typed.read_bytes(), LIMIT, ocr=must_not_run)
    assert pages and not any(page.from_ocr for page in pages)


def test_a_scan_over_the_page_limit_is_refused_whole():
    with pytest.raises(AppError) as error:
        load_document("long.pdf", scanned_pdf("a", "b", "c"), LIMIT, ocr=fake_ocr, max_ocr_pages=2)
    assert error.value.code == "TOO_MANY_SCANNED_PAGES"


def test_a_scan_where_ocr_finds_nothing_is_reported_as_no_text():
    with pytest.raises(AppError) as error:
        load_document("blank.pdf", scanned_pdf(""), LIMIT, ocr=lambda data, numbers: {})
    assert error.value.code == "NO_TEXT_EXTRACTED"


def test_missing_ocr_packages_give_a_clear_error():
    def unavailable(data, page_numbers):
        raise OcrUnavailable("No module named 'rapidocr_onnxruntime'")

    with pytest.raises(AppError) as error:
        load_document("scan.pdf", scanned_pdf("text"), LIMIT, ocr=unavailable)
    assert error.value.code == "OCR_UNAVAILABLE"


def test_ocr_can_be_switched_off():
    client = make_client(enable_ocr=False)
    assert_error(upload(client, "scan.pdf", scanned_pdf("Invoice total 4200")), 422, "NO_TEXT_EXTRACTED")


def test_boxes_are_joined_in_reading_order():
    def box(left, top, text):
        return ([[left, top], [left + 100, top], [left + 100, top + 20], [left, top + 20]], text, 0.9)

    result = [box(300, 102, "Sharma"), box(10, 200, "Date: 4 March"), box(10, 100, "Name:"), box(150, 98, "Priya")]

    assert lines_in_reading_order(result) == "Name: Priya Sharma\nDate: 4 March"


def test_a_real_scan_is_read_and_becomes_searchable():
    """End to end with the real OCR model: upload a picture of text, then find it by asking."""
    scan = scanned_pdf("Refund policy\nRefunds are issued within 14 days of purchase.")
    try:
        ocr_pdf_pages(scan, [1])
    except OcrUnavailable as exc:
        pytest.skip(f"OCR packages not usable here: {exc}")
    client = make_client()

    response = upload(client, "refunds.pdf", scan)

    assert response.status_code == 201, response.text
    assert response.json()["ocr_pages"] == 1
    sources = client.post("/ask", json={"question": "When are refunds issued?"}).json()["sources"]
    assert "14 days" in sources[0]["excerpt"]


def test_loading_a_folder_skips_a_scan_when_ocr_is_missing(tmp_path, monkeypatch):
    def unavailable(data, page_numbers, **options):
        raise OcrUnavailable("No module named 'rapidocr_onnxruntime'")

    monkeypatch.setattr("app.pipeline.ocr_pdf_pages", unavailable)
    (tmp_path / "scan.pdf").write_bytes(scanned_pdf("Invoice total 4200"))
    (tmp_path / "notes.txt").write_text("Refunds are issued within 14 days.", encoding="utf-8")
    service = make_service()

    ingested = service.ingest_directory(str(tmp_path))

    assert [doc.doc_name for doc in ingested] == ["notes.txt"]


# ── Optional second reading by a vision model ────────────────────────────────
def _real_ocr_or_skip(scan: bytes) -> None:
    try:
        ocr_pdf_pages(scan, [1])
    except OcrUnavailable as exc:
        pytest.skip(f"OCR packages not usable here: {exc}")


def test_page_confidence_is_set_by_the_weakest_lines_not_the_average():
    def line(confidence):
        return ([[0, 0], [1, 0], [1, 1], [0, 1]], "text", confidence)

    clean = [line(0.99), line(0.98), line(0.97), line(0.99)]
    half_handwritten = [line(0.99), line(0.99), line(0.99), line(0.99), line(0.7), line(0.72), line(0.74), line(0.75)]

    assert page_confidence(clean) > 0.95
    assert page_confidence(half_handwritten) < 0.8, "the printed lines must not hide the hard ones"
    assert page_confidence([]) == 0.0


def test_an_unsure_page_gets_a_second_reading():
    scan = scanned_pdf("Invoice total 4200")
    _real_ocr_or_skip(scan)
    seen = []

    def transcribe(jpeg: bytes) -> str:
        seen.append(jpeg[:3])
        return "Invoice total 4200, read by the vision model"

    texts = ocr_pdf_pages(scan, [1], transcribe=transcribe, min_confidence=1.01)

    assert texts == {1: "Invoice total 4200, read by the vision model"}
    assert seen == [b"\xff\xd8\xff"], "the page is sent once, as a JPEG"


def test_a_confident_page_is_never_sent_for_a_second_reading():
    scan = scanned_pdf("Invoice total 4200")
    _real_ocr_or_skip(scan)

    def must_not_run(jpeg: bytes) -> str:
        raise AssertionError("a page the local model read confidently left the machine")

    texts = ocr_pdf_pages(scan, [1], transcribe=must_not_run, min_confidence=0.0)

    assert "4200" in texts[1]


def test_a_failed_second_reading_keeps_the_local_text():
    scan = scanned_pdf("Invoice total 4200")
    _real_ocr_or_skip(scan)

    def broken(jpeg: bytes) -> str:
        raise TimeoutError("provider did not answer")

    texts = ocr_pdf_pages(scan, [1], transcribe=broken, min_confidence=1.01)

    assert "4200" in texts[1]


def test_a_transcription_that_starts_over_is_cut_at_the_repeat():
    text = "Assignment 1 cover page\nName: Priya\nDate: 4 March\n\nAssignment 1 cover page\nNam\ne: Pri"

    assert drop_repeated_tail(text) == "Assignment 1 cover page\nName: Priya\nDate: 4 March"
    assert drop_repeated_tail("Name: Priya\nDate: 4 March") == "Name: Priya\nDate: 4 March"


def test_vision_fallback_is_off_by_default_and_needs_a_key():
    assert make_service().vision is None
    assert make_service(ocr_vision_fallback=True).vision is None, "the fake provider has no key"
    service = make_service(ocr_vision_fallback=True, llm_provider="groq", groq_api_key="test-key")
    assert service.vision.model == "qwen/qwen3.8-27b"
