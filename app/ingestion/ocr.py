"""Read the text off scanned PDF pages. Used only for pages that have no text layer."""

from functools import lru_cache

RENDER_SCALE = 2  # 144 dpi: small print stays legible without making recognition slow


class OcrUnavailable(Exception):
    """The OCR packages are missing or cannot load on this machine."""


@lru_cache
def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # ImportError, or OpenCV failing to find a system library
        raise OcrUnavailable(str(exc)) from exc
    return RapidOCR()


def ocr_pdf_pages(data: bytes, page_numbers: list[int]) -> dict[int, str]:
    """Return the recognised text of each requested page (1-based). Pages with no text are left out."""
    try:
        import pypdfium2
    except Exception as exc:
        raise OcrUnavailable(str(exc)) from exc
    engine = _engine()

    texts: dict[int, str] = {}
    pdf = pypdfium2.PdfDocument(data)
    try:
        for number in page_numbers:
            image = pdf[number - 1].render(scale=RENDER_SCALE).to_numpy()
            result, _ = engine(image)
            text = lines_in_reading_order(result or [])
            if text:
                texts[number] = text
    finally:
        pdf.close()
    return texts


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
