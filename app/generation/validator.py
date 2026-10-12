"""Checks on the model's reply. Nothing reaches the user unless it survives these."""

import json
import re
from dataclasses import dataclass, field

from app.generation.excerpts import content_terms
from app.generation.llm_base import LLMBadResponse

NOT_AVAILABLE = "The information is not available in the provided documents."
ABSTAIN_SENTINEL = "INSUFFICIENT_CONTEXT"


@dataclass
class ValidatedAnswer:
    answerable: bool
    answer: str
    citations: list[str] = field(default_factory=list)  # valid source labels, in cited order
    abstain_reason: str | None = None
    dropped_citations: list[str] = field(default_factory=list)


def parse_json_object(raw: str) -> dict:
    """Parse the model's reply as a JSON object, tolerating code fences and stray prose around it."""
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMBadResponse("reply contained no JSON object")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMBadResponse("reply was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise LLMBadResponse("reply was not a JSON object")
    return payload


def parse_answer(raw: str) -> dict:
    payload = parse_json_object(raw)
    if "answer" not in payload or "answerable" not in payload:
        raise LLMBadResponse("reply is missing 'answer' or 'answerable'")
    return payload


def parse_sub_questions(raw: str) -> list[str]:
    items = parse_json_object(raw).get("sub_questions", [])
    return [item.strip() for item in items if isinstance(item, str) and item.strip()] if isinstance(items, list) else []


def normalise_label(value) -> str | None:
    match = re.fullmatch(r"\[?\s*[sS]?(\d+)\s*\]?", str(value).strip())
    return f"S{int(match.group(1))}" if match else None


def validate_answer(payload: dict, valid_labels: set[str]) -> ValidatedAnswer:
    answer = str(payload.get("answer") or "").strip()
    if payload.get("answerable") is not True or not answer or ABSTAIN_SENTINEL in answer.upper():
        return ValidatedAnswer(False, NOT_AVAILABLE, abstain_reason="model_abstained")

    # Sources the model itself judged to be distractors or irrelevant cannot back the answer.
    rejected = set()
    for entry in payload.get("evidence_check") or []:
        if isinstance(entry, dict) and str(entry.get("verdict", "")).strip().lower() in {"distractor", "irrelevant"}:
            rejected.add(normalise_label(entry.get("source")))

    kept: list[str] = []
    dropped: list[str] = []
    raw_citations = payload.get("citations")
    for raw in raw_citations if isinstance(raw_citations, list) else []:
        label = normalise_label(raw)
        if label in valid_labels and label not in rejected:
            if label not in kept:
                kept.append(label)
        else:
            dropped.append(str(raw))

    if not kept:
        return ValidatedAnswer(False, NOT_AVAILABLE, abstain_reason="no_valid_citations", dropped_citations=dropped)

    clean = re.sub(r"\s*[\[(]S\d+(?:\s*,\s*S\d+)*[\])]", "", answer).strip()
    return ValidatedAnswer(True, clean, citations=kept, dropped_citations=dropped)


_NUMBER = re.compile(r"\d+(?:[ \u00a0\u202f,.]\d+)*")


_NUMBER_WORDS = {
    word: str(value)
    for value, word in enumerate(
        ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
    )
}
_NUMBER_WORD = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", flags=re.IGNORECASE)


def spell_numbers_as_digits(text: str) -> str:
    """Turn "four actions" into "4 actions", so a passage saying "four" supports an answer saying "4"."""
    return _NUMBER_WORD.sub(lambda match: _NUMBER_WORDS[match.group().lower()], text)


def _numbers(text: str) -> set[str]:
    """Every figure in the text, in one spelling: "20 000 000" equals "20,000,000" and "8.00" equals "8"."""
    figures = set()
    for match in _NUMBER.findall(text):
        figure = re.sub(r"[ \u00a0\u202f,]", "", match).rstrip(".")
        if "." in figure:
            figure = figure.rstrip("0").rstrip(".")
        figures.add(figure)
    return figures


def unsupported_numbers(answer: str, question: str, cited_texts: list[str]) -> list[str]:
    """Figures in the answer that appear neither in the cited passages nor in the question.

    An invented number is the most common and most damaging kind of hallucination, and it is cheap
    to catch. This is a warning, not a refusal: a correct answer may contain a figure the model
    worked out (a difference or a total) that is not written anywhere.
    """
    # Number words are expanded on the source side only: "four" in a passage backs "4" in the answer.
    known = _numbers(spell_numbers_as_digits(question))
    for text in cited_texts:
        known |= _numbers(spell_numbers_as_digits(text))
    return sorted(_numbers(answer) - known)


def wording_is_in_sources(answer: str, cited_texts: list[str]) -> bool:
    """False when not one content word of the answer appears in the passages it cites.

    Such an answer was inferred, calculated or taken from the model's own knowledge. It may still be
    right, so this is a warning too, but the reader should know the evidence does not state it.
    """
    words = content_terms(answer) - {"yes"}
    if not words:
        return True
    return any(words & content_terms(text) for text in cited_texts)
