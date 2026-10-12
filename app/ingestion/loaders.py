"""Turn an uploaded file into pages of text, rejecting anything we cannot handle."""

import io
from pathlib import Path

from app.domain import Page
from app.errors import AppError

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


def load_document(filename: str, data: bytes, max_bytes: int, max_pdf_pages: int = 500) -> list[Page]:
    extension = Path(filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError("UNSUPPORTED_FILE_TYPE", "Only PDF, TXT, MD are accepted", 415)
    if len(data) == 0:
        raise AppError("EMPTY_FILE", "The uploaded file is empty", 422)
    if len(data) > max_bytes:
        raise AppError("FILE_TOO_LARGE", f"File exceeds the {max_bytes // (1024 * 1024)} MB limit", 413)

    pages = _load_pdf(data, max_pdf_pages) if extension == ".pdf" else _load_text(data)
    pages = [page for page in pages if page.text.strip()]
    if not pages:
        raise AppError(
            "NO_TEXT_EXTRACTED",
            "No text could be extracted. Scanned PDFs need OCR, which is not supported.",
            422,
        )
    return pages


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
