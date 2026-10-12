"""Scoring rules for the evaluation. Each check returns None when it does not apply to a question."""

import math
import re
import unicodedata

from app.generation.validator import spell_numbers_as_digits
from app.schemas import EvalQuestion, EvalResult, EvalSummary


def keywords_match(answer: str, keywords: list[str]) -> bool:
    """Every keyword must appear in the answer. "a||b" is satisfied by either alternative."""
    text = _plain(answer)
    return all(any(_plain(option.strip()) in text for option in keyword.split("||")) for keyword in keywords)


def _plain(text: str) -> str:
    """Lower-case and fold typographic variants: models often write "10 000 000" with non-breaking spaces."""
    text = spell_numbers_as_digits(unicodedata.normalize("NFKC", text)).lower()
    return re.sub(r"[‐-―]", "-", " ".join(text.split()))


def _squash(text: str) -> str:
    return " ".join(text.lower().split())


def evidence_found(evidence: list[str], chunk_texts: list[str]) -> bool:
    """Every evidence string appears in some retrieved chunk, ignoring case and line breaks."""
    chunks = [_squash(text) for text in chunk_texts]
    return all(any(_squash(item) in chunk for chunk in chunks) for item in evidence)


# ── Ranked-retrieval metrics (no LLM involved) ────────────────────────────────
def evidence_ranks(evidence: list[str], ranked_texts: list[str]) -> list[int | None]:
    """For each gold evidence string, the 1-based rank of the first retrieved chunk containing it."""
    chunks = [_squash(text) for text in ranked_texts]
    ranks: list[int | None] = []
    for item in evidence:
        needle = _squash(item)
        ranks.append(next((rank for rank, chunk in enumerate(chunks, start=1) if needle in chunk), None))
    return ranks


def recall_at_k(ranks: list[int | None], k: int) -> float:
    """Share of the gold evidence found in the top k. A two-fact question needs both for 1.0."""
    return sum(rank is not None and rank <= k for rank in ranks) / len(ranks)


def reciprocal_rank(ranks: list[int | None]) -> float:
    """1 / rank of the first relevant chunk, or 0 if none was retrieved."""
    found = [rank for rank in ranks if rank is not None]
    return 1 / min(found) if found else 0.0


def ndcg_at_k(ranks: list[int | None], k: int) -> float:
    """Rewards putting the gold evidence near the top. Each evidence item counts once, at its first hit."""
    dcg = sum(1 / math.log2(rank + 1) for rank in ranks if rank is not None and rank <= k)
    ideal = sum(1 / math.log2(position + 1) for position in range(1, min(len(ranks), k) + 1))
    return min(1.0, dcg / ideal) if ideal else 0.0


def score_question(
    question: EvalQuestion,
    *,
    answerable: bool,
    answer: str,
    retrieved: list[str],
    cited: list[str],
    latency_ms: float,
    retrieved_texts: list[str] | None = None,
) -> EvalResult:
    expected = set(question.expected_sources)
    abstention_ok = answerable == question.expected_answerable

    # Retrieval hit: every expected document shows up in the retrieved set and, where the question
    # names the supporting text, that text is inside a retrieved chunk. The second part is what makes
    # this meaningful on a long document, where "the right file" is always retrieved.
    retrieval_hit = expected.issubset(retrieved) if expected else None
    if question.expected_evidence:
        retrieval_hit = bool(retrieval_hit) and evidence_found(question.expected_evidence, retrieved_texts or [])

    citation_ok = keywords_ok = None
    if question.expected_answerable:
        # Citations must be present and must all point at expected documents.
        citation_ok = bool(cited) and set(cited).issubset(expected) if expected else bool(cited)
        if question.expected_keywords:
            keywords_ok = answerable and keywords_match(answer, question.expected_keywords)

    distractor_ok = None
    if question.type == "distractor":
        distractor_ok = abstention_ok and not set(cited) & set(question.distractor_sources)
        if question.expected_answerable:
            distractor_ok = distractor_ok and bool(set(cited) & expected)

    checks = [abstention_ok, citation_ok, keywords_ok, distractor_ok]
    return EvalResult(
        id=question.id,
        type=question.type,
        question=question.question,
        passed=all(check for check in checks if check is not None),
        expected_answerable=question.expected_answerable,
        answerable=answerable,
        retrieved=retrieved,
        cited=cited,
        retrieval_hit=retrieval_hit,
        citation_ok=citation_ok,
        keywords_ok=keywords_ok,
        distractor_ok=distractor_ok,
        latency_ms=latency_ms,
        answer=answer,
    )


def _rate(values: list[bool | None]) -> float | None:
    applicable = [value for value in values if value is not None]
    return round(sum(applicable) / len(applicable), 3) if applicable else None


def summarise(results: list[EvalResult]) -> EvalSummary:
    scored = [r for r in results if r.error is None]
    return EvalSummary(
        total=len(results),
        passed=sum(r.passed for r in results),
        retrieval_hit_at_k=_rate([r.retrieval_hit for r in scored]),
        # A question that errored counts as a wrong abstention decision, never as a free pass.
        abstention_accuracy=_rate([r.answerable == r.expected_answerable for r in results]),
        citation_correctness=_rate([r.citation_ok for r in scored]),
        answer_keyword_accuracy=_rate([r.keywords_ok for r in scored]),
        distractor_resilience=_rate([r.distractor_ok for r in scored]),
        faithfulness=_rate([r.faithful for r in scored]),
        answer_relevance=_rate([r.relevant for r in scored]),
        avg_latency_ms=round(sum(r.latency_ms for r in results) / len(results), 1) if results else 0.0,
    )
