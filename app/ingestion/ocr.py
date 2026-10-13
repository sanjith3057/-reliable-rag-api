"""Read the text off scanned PDF pages. Used only for pages that have no text layer."""

import io
from collections.abc import Callable
from functools import lru_cache

from app.logging import get_logger

logger = get_logger(__name__)

RENDER_SCALE = 2  # 144 dpi: small print stays legible without making recognition slow

# Reads a page image (JPEG bytes) and returns its text. See app/ingestion/vision.py.
Transcriber = Callable[[bytes], str]


class OcrUnavailable(Exception):
    """The OCR packages are missing or cannot load on this machine."""


@lru_cache
def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # ImportError, or OpenCV failing to find a system library
        raise OcrUnavailable(str(exc)) from exc
    return RapidOCR()


def ocr_pdf_pages(
    data: bytes,
    page_numbers: list[int],
    transcribe: Transcriber | None = None,
    min_confidence: float = 0.85,
) -> dict[int, str]:
    """Return the recognised text of each requested page (1-based). Pages with no text are left out.

    With `transcribe`, a page the local model was unsure of (see `page_confidence`) is read a second
    time by that function, and its text is used if it returns any.
    """
    try:
        import pypdfium2
    except Exception as exc:
        raise OcrUnavailable(str(exc)) from exc
    engine = _engine()

    texts: dict[int, str] = {}
    pdf = pypdfium2.PdfDocument(data)
    try:
        for number in page_numbers:
            bitmap = pdf[number - 1].render(scale=RENDER_SCALE)
            result, _ = engine(bitmap.to_numpy())
            text = lines_in_reading_order(result or [])
            if transcribe is not None and page_confidence(result or []) < min_confidence:
                text = _second_reading(transcribe, bitmap, number) or text
            if text:
                texts[number] = text
    finally:
        pdf.close()
    return texts


def page_confidence(result: list) -> float:
    """How sure the local model was of a page: the confidence of its weakest quarter of lines.

    The average hides a hard page, because printed headers and footers read at close to 1.0 and
    pull it up. A page with nothing recognised scores 0.
    """
    scores = sorted(float(confidence) for _, text, confidence in result if text.strip())
    return scores[len(scores) // 4] if scores else 0.0


def _second_reading(transcribe: Transcriber, bitmap, number: int) -> str:
    buffer = io.BytesIO()
    bitmap.to_pil().convert("RGB").save(buffer, format="JPEG", quality=85)
    try:
        return transcribe(buffer.getvalue()).strip()
    except Exception as exc:  # a failed second reading must not lose the first one
        logger.warning("vision transcription failed for page %d: %s", number, type(exc).__name__)
        return ""


def lines_in_reading_order(result: list) -> str:
    """Join recognised boxes into lines, top to bottom and left to right.

    Each item is (box, text, confidence), where box is four [x, y] corners starting top-left.
    Boxes whose tops are within half a box height of each other are treated as one line.
    """
    boxes = sorted(
        ((box[0][1], box[0][0], box[3][1] - box[0][1], text.strip()) for box, text, _ in result if text.strip()),
        key=lambda item: item[0],
    )
    rows: list[list[tuple]] = []
    for top, left, height, text in boxes:
        if rows and abs(top - rows[-1][0][0]) <= max(height, rows[-1][0][2]) / 2:
            rows[-1].append((top, left, height, text))
        else:
            rows.append([(top, left, height, text)])
    return "\n".join(" ".join(item[3] for item in sorted(row, key=lambda item: item[1])) for row in rows)
