"""Runs an evaluation set through the live pipeline. Shared by POST /eval and eval/run_eval.py."""

import json
import time
from datetime import datetime
from pathlib import Path

from app.errors import AppError
from app.evaluation.metrics import score_question, summarise
from app.generation.validator import parse_json_object
from app.pipeline import RagService
from app.schemas import EvalQuestion, EvalReport, EvalResult


def load_questions(eval_dir: str, dataset: str) -> list[EvalQuestion]:
    path = Path(eval_dir) / f"questions_{dataset}.json"
    if not path.is_file():
        raise AppError("EVAL_SET_NOT_FOUND", f"Evaluation set '{path.as_posix()}' does not exist", 404)
    return [EvalQuestion(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


JUDGE_SYSTEM_PROMPT = """You are a strict grader of a question-answering system.

You are given a question, the system's answer, and the passages the answer cited.

Return one JSON object: {"faithful": true or false, "relevant": true or false, "unsupported": ["..."]}

- "faithful" is true only if every factual claim in the answer is stated in the passages or follows
  directly from them. Use only the passages, not your own knowledge.
- "relevant" is true if the answer addresses what the question asked.
- "unsupported" lists the claims, if any, that the passages do not support."""


def run_evaluation(
    service: RagService,
    questions: list[EvalQuestion],
    *,
    top_k: int | None = None,
    dataset: str = "custom",
    judge: bool = False,
) -> EvalReport:
    results = [_run_one(service, question, top_k, judge) for question in questions]
    settings = service.settings
    return EvalReport(
        run_id=datetime.now().isoformat(timespec="seconds"),
        dataset=dataset,
        config={
            "llm": f"{service.llm.name}/{service.llm.model}",
            "embedder": service.embedder.name,
            "top_k": top_k or settings.top_k,
            "similarity_threshold": settings.similarity_threshold,
            "hybrid": settings.enable_hybrid,
            "reranker": settings.enable_reranker,
            "judge": judge,
        },
        summary=summarise(results),
        results=results,
    )


def _run_one(service: RagService, question: EvalQuestion, top_k: int | None, judge: bool = False) -> EvalResult:
    settings = service.settings
    outcome, error, start = None, None, time.perf_counter()
    for attempt in range(settings.eval_rate_limit_retries + 1):
        start = time.perf_counter()  # latency is that of the attempt that produced the result
        try:
            outcome = service.ask(question.question, top_k)
            break
        except AppError as exc:
            error = exc
            if exc.code not in {"LLM_UNAVAILABLE", "LLM_RATE_LIMITED"} or attempt == settings.eval_rate_limit_retries:
                break
            # A short per-minute limit is worth waiting out; a daily quota is not.
            asked = float((exc.headers or {}).get("Retry-After", 0))
            if asked > 2 * max(settings.eval_rate_limit_pause_s, 1):
                break
            time.sleep(max(settings.eval_rate_limit_pause_s, asked))
    if outcome is None:
        # One failed question (for example an LLM outage) must not sink the whole run.
        return EvalResult(
            id=question.id,
            type=question.type,
            question=question.question,
            passed=False,
            expected_answerable=question.expected_answerable,
            answerable=None,
            retrieved=[],
            cited=[],
            retrieval_hit=None,
            citation_ok=None,
            keywords_ok=None,
            distractor_ok=None,
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
            error=error.code if error else "UNKNOWN",
        )
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    result = score_question(
        question,
        answerable=outcome.response.answerable,
        answer=outcome.response.answer,
        retrieved=_unique(item.chunk.doc_name for item in outcome.retrieved),
        cited=_unique(source.doc_name for source in outcome.response.sources),
        latency_ms=latency_ms,
        retrieved_texts=[item.chunk.text for item in outcome.retrieved],
    )
    if judge and outcome.response.answerable:
        result.faithful, result.relevant = _judge(service, question.question, outcome)
    return result


def _judge(service: RagService, question: str, outcome) -> tuple[bool | None, bool | None]:
    """Ask the LLM whether the answer is supported by what it cited. None if the judge call fails."""
    passages = "\n\n".join(f"[{number}] {item.chunk.text}" for number, item in enumerate(outcome.cited, start=1))
    prompt = f"Question: {question}\n\nAnswer: {outcome.response.answer}\n\nPassages:\n{passages}"
    try:
        verdict = service.call_llm(JUDGE_SYSTEM_PROMPT, prompt, parse_json_object)
    except AppError:
        return None, None
    faithful, relevant = verdict.get("faithful"), verdict.get("relevant")
    return (faithful if isinstance(faithful, bool) else None, relevant if isinstance(relevant, bool) else None)


def save_report(path: Path | None, report: EvalReport) -> None:
    """Keep the latest report on disk so it survives a restart. Failure to write is not fatal."""
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(), encoding="utf-8")
    except OSError:
        pass


def load_report(path: Path | None) -> EvalReport | None:
    if path is None or not path.is_file():
        return None
    try:
        return EvalReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _unique(names) -> list[str]:
    return list(dict.fromkeys(names))


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def render_markdown(report: EvalReport) -> str:
    s = report.summary
    config = ", ".join(f"{key}={value}" for key, value in report.config.items())
    lines = [
        f"# Evaluation results ({report.dataset} set)",
        "",
        f"Run: {report.run_id}  ",
        f"Config: {config}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Questions passed | {s.passed} / {s.total} |",
        f"| Retrieval hit@k | {_fmt(s.retrieval_hit_at_k)} |",
        f"| Abstention accuracy | {_fmt(s.abstention_accuracy)} |",
        f"| Citation correctness | {_fmt(s.citation_correctness)} |",
        f"| Answer keyword accuracy | {_fmt(s.answer_keyword_accuracy)} |",
        f"| Distractor resilience | {_fmt(s.distractor_resilience)} |",
        *(
            [
                f"| Faithfulness (LLM-judged) | {_fmt(s.faithfulness)} |",
                f"| Answer relevance (LLM-judged) | {_fmt(s.answer_relevance)} |",
            ]
            if report.config.get("judge")
            else []
        ),
        f"| Average latency | {s.avg_latency_ms:.0f} ms |",
        "",
        "| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in report.results:
        got = "error: " + r.error if r.error else str(r.answerable).lower()
        lines.append(
            f"| {r.id} | {r.type} | {'yes' if r.passed else 'NO'} | "
            f"{str(r.expected_answerable).lower()} / {got} | {', '.join(r.cited) or '-'} | {r.latency_ms:.0f} ms |"
        )
    return "\n".join(lines) + "\n"
