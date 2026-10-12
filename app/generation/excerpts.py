"""Pick the few sentences of a cited chunk that actually carry the evidence.

Done locally, with no extra LLM call. The lines that contain the words of the answer come
first, because they are what a reader needs to check it. If none do (the answer was
paraphrased), sentences are ranked by similarity to the question and answer instead.
"""

import re

from app.retrieval.embedder import Embedder, cosine

_MIN_SENTENCE_CHARS = 20
_STOPWORDS = frozenset(
    "the and for are was were has have had not but with from that this these those their there "
    "its his her she him they them you your our per can may will would should than then into "
    "about over under each any all one two also been being which who whom what when where how".split()
)


_LIST_ITEM = re.compile(r"(\d+\.|[-*•#])\s")


def _is_soft_wrap(line: str, following: str) -> bool:
    """True when a line break is only a PDF wrapping one sentence, not the end of a field or a row."""
    if len(line) < 40 or not following or line[-1] in ".!?:":
        return False
    if following[0].islower():
        return True
    # A long line with no closing punctuation is running prose, unless the next line starts something new.
    return len(line) >= 60 and "|" not in line and not following.isupper() and not _LIST_ITEM.match(following)


def _unwrap(text: str) -> str:
    lines = [line.strip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if out and _is_soft_wrap(out[-1], line):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return "\n".join(out)


def _clip(text: str, max_chars: int) -> str:
    """Cut at a word boundary and mark the cut, so a long excerpt does not end mid-word."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:…") + " …"


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", _unwrap(text))
    return [part.strip(" \t-*#|") for part in parts if part.strip(" \t-*#|")]


def content_terms(text: str) -> set[str]:
    """Words and numbers worth matching on: numbers of any length, words of three letters or more."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t.isdigit() or (len(t) >= 3 and t not in _STOPWORDS)}


def _covering(sentences: list[str], wanted: set[str], max_sentences: int) -> tuple[list[int], set[str]]:
    """Indexes of the sentences that together contain the most of the wanted words, and the words found."""
    wanted = set(wanted)
    found: set[str] = set()
    # A line in capitals is a heading or a field label. It can share a word with the answer without
    # being evidence for it, so it is only quoted when the chunk has nothing else.
    only_labels = all(sentence.isupper() for sentence in sentences)
    sentence_terms = [
        content_terms(sentence) if only_labels or not sentence.isupper() else set() for sentence in sentences
    ]
    chosen: list[int] = []
    while wanted and len(chosen) < max_sentences:
        # The sentence that adds the most still-missing words; the earliest one wins a tie.
        gain, index = max((len(terms & wanted), -i) for i, terms in enumerate(sentence_terms))
        if gain == 0:
            break
        chosen.append(-index)
        found |= sentence_terms[-index] & wanted
        wanted -= sentence_terms[-index]
    return chosen, found


def _with_label(sentences: list[str], index: int, chosen: list[int]) -> str:
    """A short form value reads better with the field label printed above it, e.g. "PREFERRED NAME Maggie"."""
    line = sentences[index]
    if len(line) < _MIN_SENTENCE_CHARS and index > 0 and index - 1 not in chosen and sentences[index - 1].isupper():
        return f"{sentences[index - 1]} {line}"
    return line


def best_excerpts(texts: list[str], question: str, answer: str, embedder: Embedder) -> list[str]:
    """One excerpt per cited chunk. Each chunk shows the part of the answer the earlier ones did not."""
    remaining = content_terms(answer)
    excerpts = []
    for text in texts:
        excerpt, found = _excerpt(text, question, answer, embedder, remaining)
        remaining -= found
        excerpts.append(excerpt)
    return excerpts


def best_excerpt(text: str, question: str, answer: str, embedder: Embedder) -> str:
    return _excerpt(text, question, answer, embedder, content_terms(answer))[0]


def _excerpt(
    text: str, question: str, answer: str, embedder: Embedder, wanted: set[str], max_sentences: int = 3
) -> tuple[str, set[str]]:
    max_chars = 400
    sentences = split_sentences(text)
    if not sentences:
        return _clip(text.strip(), max_chars), set()

    # Form fields and table cells have no closing punctuation, so every line is a candidate here.
    chosen, found = _covering(sentences, wanted, max_sentences)
    if not chosen:
        chosen, _ = _covering(sentences, content_terms(answer), max_sentences)
    if chosen:
        parts = [_with_label(sentences, i, chosen) for i in sorted(chosen)]
        return _clip(" … ".join(parts), max_chars), found
    return _closest_sentences(sentences, f"{question} {answer}", embedder, max_sentences, max_chars), set()


def _closest_sentences(sentences: list[str], query: str, embedder: Embedder, max_sentences: int, max_chars: int) -> str:

    # Headings and list labels have no closing punctuation; they are not evidence on their own.
    candidates = [s for s in sentences if len(s) >= _MIN_SENTENCE_CHARS and s[-1] in ".!?"] or sentences
    if len(candidates) == 1:
        return _clip(candidates[0], max_chars)

    query_vector = embedder.embed_query(query)
    scores = [cosine(vector, query_vector) for vector in embedder.embed_documents(candidates)]
    ranked = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)

    # Always keep the best sentence; add runners-up only if they are nearly as relevant.
    best_score = scores[ranked[0]]
    picked = [ranked[0]]
    for index in ranked[1:max_sentences]:
        if scores[index] >= 0.85 * best_score and scores[index] > 0:
            picked.append(index)

    excerpt = " … ".join(candidates[i] for i in sorted(picked))
    return _clip(excerpt, max_chars)
