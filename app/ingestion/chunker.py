"""Recursive splitter: paragraph, then line, then sentence, then word.

Text is first broken into pieces no longer than the chunk size, trying the coarsest
boundary first, then the pieces are packed back into chunks. Each new chunk starts
with the tail of the previous one so a fact that straddles a boundary stays whole
in at least one chunk.
"""

import re

from app.domain import Chunk, Page

_SEPARATORS = [r"\n\s*\n", r"\n", r"(?<=[.!?])\s+", r"\s+"]


def split_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("need chunk_size > overlap >= 0")
    pieces = _split(text.strip(), chunk_size, _SEPARATORS)
    return _pack(pieces, chunk_size, overlap)


def chunk_pages(
    pages: list[Page], doc_id: str, doc_name: str, chunk_size: int = 800, overlap: int = 120
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for text in split_text(page.text, chunk_size, overlap):
            index = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{index}",
                    doc_id=doc_id,
                    doc_name=doc_name,
                    page=page.number,
                    index=index,
                    text=text,
                )
            )
    return chunks


def _split(text: str, size: int, separators: list[str]) -> list[str]:
    if len(text) <= size:
        return [text] if text else []
    for position, separator in enumerate(separators):
        parts = _split_keeping_separator(text, separator)
        if len(parts) > 1:
            pieces: list[str] = []
            for part in parts:
                pieces.extend(_split(part, size, separators[position + 1 :]))
            return pieces
    # No boundary left (one very long token): cut hard.
    return [text[i : i + size] for i in range(0, len(text), size)]


def _split_keeping_separator(text: str, separator: str) -> list[str]:
    """Split on the pattern but leave each separator attached to the piece before it."""
    tokens = re.split(f"({separator})", text)
    parts = [tokens[i] + (tokens[i + 1] if i + 1 < len(tokens) else "") for i in range(0, len(tokens), 2)]
    return [part for part in parts if part]


def _pack(pieces: list[str], size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for piece in pieces:
        if current and current_len + len(piece) > size:
            chunks.append("".join(current).strip())
            current, current_len = _tail(current, overlap)
            if current_len + len(piece) > size:
                current, current_len = [], 0
        current.append(piece)
        current_len += len(piece)
    if current:
        chunks.append("".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _tail(pieces: list[str], overlap: int) -> tuple[list[str], int]:
    tail: list[str] = []
    length = 0
    for piece in reversed(pieces):
        if length + len(piece) > overlap:
            break
        tail.insert(0, piece)
        length += len(piece)
    return tail, length
