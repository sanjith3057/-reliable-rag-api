"""Runs an evaluation set through the live pipeline. Shared by POST /eval and eval/run_eval.py."""

import json
import time
from datetime import datetime
from pathlib import Path

from app.errors import AppError
from app.evaluation.metrics import score_question, summarise
from app.pipeline import RagService
from app.schemas import EvalQuestion, EvalReport, EvalResult


def load_questions(eval_dir: str, dataset: str) -> list[EvalQuestion]:
    path = Path(eval_dir) / f"questions_{dataset}.json"
    if not path.is_file():
        raise AppError("EVAL_SET_NOT_FOUND", f"Evaluation set '{path.as_posix()}' does not exist", 404)
    return [EvalQuestion(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


def run_evaluation(
    service: RagService, questions: list[EvalQuestion], *, top_k: int | None = None, dataset: str = "custom"
) -> EvalReport:
    results = [_run_one(service, question, top_k) for question in questions]
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
        },
        summary=summarise(results),
        results=results,
    )


def _run_one(service: RagService, question: EvalQuestion, top_k: int | None) -> EvalResult:
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
    return score_question(
        question,
        answerable=outcome.response.answerable,
        answer=outcome.response.answer,
        retrieved=_unique(item.chunk.doc_name for item in outcome.retrieved),
        cited=_unique(source.doc_name for source in outcome.response.sources),
        latency_ms=latency_ms,
        retrieved_texts=[item.chunk.text for item in outcome.retrieved],
    )


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
