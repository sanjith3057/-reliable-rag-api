"""Turn an uploaded file into pages of text, rejecting anything we cannot handle."""

import io
import logging
from collections.abc import Callable
from pathlib import Path

from app.domain import Page
from app.errors import AppError
from app.ingestion.ocr import OcrUnavailable

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}

# Reads the text off the given 1-based pages of a PDF. See app/ingestion/ocr.py.
Ocr = Callable[[bytes, list[int]], dict[int, str]]


def load_document(
    filename: str,
    data: bytes,
    max_bytes: int,
    max_pdf_pages: int = 500,
    ocr: Ocr | None = None,
    max_ocr_pages: int = 25,
) -> list[Page]:
    """Return the pages that have text. With `ocr`, PDF pages without a text layer are read as images."""
    extension = Path(filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError("UNSUPPORTED_FILE_TYPE", "Only PDF, TXT, MD are accepted", 415)
    if len(data) == 0:
        raise AppError("EMPTY_FILE", "The uploaded file is empty", 422)
    if len(data) > max_bytes:
        raise AppError("FILE_TOO_LARGE", f"File exceeds the {max_bytes // (1024 * 1024)} MB limit", 413)

    pages = _load_pdf(data, max_pdf_pages) if extension == ".pdf" else _load_text(data)
    if extension == ".pdf" and ocr is not None:
        pages = _read_scanned_pages(data, pages, ocr, max_ocr_pages)
    pages = [page for page in pages if page.text.strip()]
    if not pages:
        raise AppError("NO_TEXT_EXTRACTED", "No text could be extracted from this file.", 422)
    return pages


def _read_scanned_pages(data: bytes, pages: list[Page], ocr: Ocr, max_ocr_pages: int) -> list[Page]:
    scanned = [page.number for page in pages if not page.text.strip()]
    if not scanned:
        return pages
    if len(scanned) > max_ocr_pages:
        if len(scanned) == len(pages):
            # Reading only the first few pages of a scan would look like success and answer badly.
            raise AppError(
                "TOO_MANY_SCANNED_PAGES",
                f"This PDF is {len(scanned)} scanned pages. Scanned PDFs are limited to {max_ocr_pages} pages.",
                422,
            )
        # Mostly typed, with many picture-only pages: read the first ones, keep the typed text.
        logger.warning("ocr skipped %d pages over the limit", len(scanned) - max_ocr_pages)
        scanned = scanned[:max_ocr_pages]
    try:
        recognised = ocr(data, scanned)
    except OcrUnavailable as exc:
        if len(scanned) == len(pages):
            raise AppError(
                "OCR_UNAVAILABLE",
                "This PDF is scanned and the OCR packages are not installed on this server.",
                422,
            ) from exc
        logger.warning("ocr unavailable, scanned pages skipped: %s", exc)
        return pages
    except Exception as exc:
        raise AppError("UNREADABLE_FILE", "The scanned pages of this PDF could not be read", 422) from exc
    return [
        Page(page.number, recognised[page.number], from_ocr=True) if page.number in recognised else page
        for page in pages
    ]


def _load_pdf(data: bytes, max_pages: int) -> list[Page]:
    from pypdf import PdfReader  # lazy: only needed when a PDF is actually uploaded

    try:
        reader = PdfReader(io.BytesIO(data))
        page_count = len(reader.pages)
    except Exception as exc:  # pypdf raises many different types on corrupt input
        raise AppError("UNREADABLE_FILE", "The PDF is corrupt or could not be parsed", 422) from exc
    # A small file can declare a huge number of pages; refuse before spending time extracting them.
    if page_count > max_pages:
        raise AppError("TOO_MANY_PAGES", f"PDFs are limited to {max_pages} pages", 422)
    try:
        return [Page(number=i, text=page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)]
    except Exception as exc:
        raise AppError("UNREADABLE_FILE", "The PDF is corrupt or could not be parsed", 422) from exc


def _load_text(data: bytes) -> list[Page]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("UNREADABLE_FILE", "The file is not valid UTF-8 text", 422) from exc
    return [Page(number=None, text=text)]
