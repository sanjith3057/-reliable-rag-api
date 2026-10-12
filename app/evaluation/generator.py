"""Write an evaluation set from whatever documents are in the library.

The bundled question sets only prove the system works on the bundled documents. This lets
anyone measure it on their own: sample passages, have the LLM write one question per passage,
and keep a draft only if the evidence it quotes really is in that passage.
"""

import random

from app.domain import Chunk
from app.errors import AppError
from app.evaluation.metrics import evidence_found
from app.generation.validator import parse_json_object
from app.logging import get_logger, log_event
from app.pipeline import RagService
from app.schemas import EvalQuestion, GenerateResponse

logger = get_logger(__name__)

_MIN_PASSAGE_CHARS = 200
_MAX_KEYWORD_WORDS = 4  # a longer "keyword" is a sentence, and a correct answer rarely repeats it word for word

GENERATE_SYSTEM_PROMPT = """You write test questions for a document question-answering system.

You are given one passage. Write ONE question that the passage answers with a specific fact.

Return one JSON object:
{"question": "...", "answer_keyword": "...", "evidence": "..."}

- "question" must stand on its own: name the subject, never say "the passage" or "this document".
- "answer_keyword" is the shortest text, copied exactly from the passage, that any correct answer must
  contain: a number, a name, or at most 3 words. Never a whole sentence.
- "evidence" is an exact quote of 5 to 15 words from the passage that contains the answer.
- If the passage states no clear fact, return {"question": ""}."""

# No document set written for a real purpose answers these, so a correct system must refuse them.
# They check the one thing generated questions cannot: that the model does not answer from memory.
GENERAL_KNOWLEDGE_TRAPS = [
    "What is the boiling point of water at sea level in degrees Celsius?",
    "Which country won the 2018 FIFA World Cup?",
    "What is the capital city of Australia?",
]


def generate_questions(service: RagService, n: int = 8, seed: int | None = None) -> GenerateResponse:
    passages = [chunk for chunk in service.store.all_chunks() if len(chunk.text) >= _MIN_PASSAGE_CHARS]
    if not passages:
        raise AppError("NO_DOCUMENTS", "No documents with enough text to write questions from. Upload one first.", 409)

    # Sorted first so that a seed picks the same passages whatever order the store returns them in.
    passages.sort(key=lambda chunk: chunk.chunk_id)
    sample = random.Random(seed).sample(passages, min(n, len(passages)))

    questions: list[EvalQuestion] = []
    skipped = 0
    seen_evidence: set[str] = set()
    for chunk in sample:
        draft = _draft(service, chunk)
        # Overlapping chunks share text, so two passages can yield the same question: keep the first.
        if draft is None or draft["evidence"].lower() in seen_evidence:
            skipped += 1
            continue
        seen_evidence.add(draft["evidence"].lower())
        questions.append(
            EvalQuestion(
                id=f"gen{len(questions) + 1:02d}",
                type="answerable",
                question=draft["question"],
                expected_answerable=True,
                expected_sources=[chunk.doc_name],
                expected_keywords=[draft["answer_keyword"]],
                expected_evidence=[draft["evidence"]],
            )
        )
    for number, trap in enumerate(GENERAL_KNOWLEDGE_TRAPS, start=1):
        questions.append(
            EvalQuestion(id=f"trap{number}", type="unanswerable", question=trap, expected_answerable=False)
        )

    log_event(logger, "eval_generated", requested=n, written=len(questions), skipped=skipped)
    return GenerateResponse(questions=questions, skipped=skipped)


def _draft(service: RagService, chunk: Chunk) -> dict | None:
    """One question for one passage, or None if the model's draft cannot be verified against it."""
    try:
        draft = service.call_llm(GENERATE_SYSTEM_PROMPT, f"Passage:\n{chunk.text}", parse_json_object)
    except AppError as exc:
        if exc.code == "LLM_RATE_LIMITED":
            raise  # a spent quota will fail every remaining passage too: stop and say so
        return None
    question = str(draft.get("question") or "").strip()
    keyword = str(draft.get("answer_keyword") or "").strip()
    evidence = str(draft.get("evidence") or "").strip()
    if not question or not keyword or not evidence or len(keyword.split()) > _MAX_KEYWORD_WORDS:
        return None
    # The model must have copied, not paraphrased: otherwise the gold labels would be wrong.
    if not evidence_found([evidence, keyword], [chunk.text]):
        return None
    return {"question": question, "answer_keyword": keyword, "evidence": evidence}
