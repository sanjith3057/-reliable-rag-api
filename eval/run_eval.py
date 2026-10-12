"""Evaluation CLI. Uses the same evaluator as POST /eval, against a clean in-memory store.

python eval/run_eval.py                  # end-to-end eval on the test set, writes eval/results.md
python eval/run_eval.py --dataset real   # end-to-end eval on the real-document set
python eval/run_eval.py --retrieval      # retrieval and fusion eval: BM25 vs dense vs hybrid vs reranked (no LLM)
python eval/run_eval.py --tune           # gate threshold sweep on the dev set (no LLM)
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.evaluation.evaluator import load_questions, render_markdown, run_evaluation  # noqa: E402
from app.evaluation.metrics import evidence_ranks, ndcg_at_k, recall_at_k, reciprocal_rank  # noqa: E402
from app.main import build_service  # noqa: E402
from app.retrieval.bm25 import BM25Index  # noqa: E402
from app.retrieval.reranker import CrossEncoderReranker  # noqa: E402
from app.retrieval.retriever import Retriever  # noqa: E402

EVAL_DIR = ROOT / "eval"
KS = (3, 5, 10)
DEPTH = max(KS)


def make_service(**overrides):
    settings = Settings(
        chroma_path="",  # in-memory: never touches the server's store
        collection_name=f"eval-{time.time_ns()}",
        sample_docs_dir=str(ROOT / "sample_docs"),
        eval_dir=str(EVAL_DIR),
        **overrides,
    )
    service = build_service(settings)
    # One mixed corpus for every question set: 8 short fictional documents plus an 88-page real PDF.
    service.ingest_directory(settings.sample_docs_dir)
    service.ingest_directory(str(ROOT / "real_docs"))
    return service


def tune() -> None:
    """Show how well each gate threshold separates answerable from unanswerable dev questions."""
    service = make_service()
    rows = []
    for q in load_questions(str(EVAL_DIR), "dev"):
        top = max(item.score for item in service.retriever.retrieve(q.question, service.settings.top_k))
        rows.append((top, q))

    print("\nTop similarity per dev question\n")
    for top, q in sorted(rows, key=lambda row: row[0], reverse=True):
        print(f"  {top:.3f}  {'answerable  ' if q.expected_answerable else 'UNANSWERABLE'}  {q.type:<12} {q.question}")

    print("\nThreshold sweep (a gate may never block an answerable question)\n")
    print("  threshold  answerable kept  unanswerable blocked")
    answerable = [top for top, q in rows if q.expected_answerable]
    unanswerable = [top for top, q in rows if not q.expected_answerable]
    for step in range(30, 85, 5):
        threshold = step / 100
        kept = sum(top >= threshold for top in answerable)
        blocked = sum(top < threshold for top in unanswerable)
        print(f"  {threshold:.2f}       {kept}/{len(answerable)}              {blocked}/{len(unanswerable)}")
    print(
        f"\n  lowest answerable score: {min(answerable):.3f}"
        f"   current threshold: {service.settings.similarity_threshold}"
    )


def _retrievers(service) -> dict:
    """Each entry maps a question to the texts of its top chunks, best first."""
    store, embedder = service.store, service.embedder
    reranker = CrossEncoderReranker(service.settings.reranker_model)
    raw_k = service.settings.raw_k
    bm25 = BM25Index(store.all_chunks())
    dense = Retriever(store, embedder)
    hybrid = Retriever(store, embedder, hybrid=True, raw_k=raw_k)
    dense_reranked = Retriever(store, embedder, reranker=reranker, raw_k=raw_k)
    hybrid_reranked = Retriever(store, embedder, hybrid=True, reranker=reranker, raw_k=raw_k)

    def texts(retriever):
        return lambda question: [item.chunk.text for item in retriever.retrieve(question, DEPTH)]

    return {
        "BM25 only": lambda question: [chunk.text for chunk in bm25.search(question, DEPTH)],
        "Dense only": texts(dense),
        "Hybrid (BM25 + dense)": texts(hybrid),
        "Dense + reranker (default)": texts(dense_reranked),
        "Hybrid + reranker": texts(hybrid_reranked),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def retrieval_eval() -> str:
    """Retrieval and fusion quality, measured on its own: no LLM is called.

    Gold labels are the `expected_evidence` strings: a chunk is relevant if it contains one.
    """
    service = make_service()
    sets = {
        "Fictional documents": [q for q in load_questions(str(EVAL_DIR), "test") if q.expected_evidence],
        "Real document (GDPR)": [q for q in load_questions(str(EVAL_DIR), "real") if q.expected_evidence],
    }
    retrievers = _retrievers(service)
    for retrieve in retrievers.values():
        retrieve("warm up")

    # ranks[mode][set] = one list of evidence ranks per question; timings in milliseconds per mode
    ranks = {mode: {name: [] for name in sets} for mode in retrievers}
    timings = {mode: [] for mode in retrievers}
    for mode, retrieve in retrievers.items():
        for name, questions in sets.items():
            for q in questions:
                start = time.perf_counter()
                ranked = retrieve(q.question)
                timings[mode].append((time.perf_counter() - start) * 1000)
                ranks[mode][name].append(evidence_ranks(q.expected_evidence, ranked))

    documents = len(service.store.list_documents())
    lines = [
        "# Retrieval and fusion evaluation",
        "",
        f"Corpus: {service.store.count()} chunks from {documents} documents. No LLM is called.",
        "A chunk counts as relevant if it contains the gold evidence text for the question.",
        "",
        "- **Recall@K**: share of the gold evidence found in the top K chunks (a two-fact question needs both).",
        "- **MRR**: 1 / rank of the first relevant chunk, averaged.",
        "- **nDCG@K**: like recall, but rewards relevant chunks for being nearer the top.",
        "",
    ]
    for name, questions in sets.items():
        lines += [
            f"## {name} ({len(questions)} questions)",
            "",
            "| Retrieval | " + " | ".join(f"Recall@{k}" for k in KS) + " | MRR | nDCG@5 | nDCG@10 |",
            "| --- |" + " --- |" * (len(KS) + 3),
        ]
        for mode in retrievers:
            per_question = ranks[mode][name]
            recalls = " | ".join(f"{_mean([recall_at_k(r, k) for r in per_question]):.2f}" for k in KS)
            mrr = _mean([reciprocal_rank(r) for r in per_question])
            ndcg = " | ".join(f"{_mean([ndcg_at_k(r, k) for r in per_question]):.2f}" for k in (5, 10))
            lines.append(f"| {mode} | {recalls} | {mrr:.2f} | {ndcg} |")
        lines.append("")

    # Does BM25 find what dense misses, and the other way round? Judged on full recall in the top 5.
    lines += [
        "## Complementarity of BM25 and dense search (top 5)",
        "",
        "| Set | Both found it | Only BM25 | Only dense | Neither |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in sets:
        pairs = list(zip(ranks["BM25 only"][name], ranks["Dense only"][name], strict=True))
        sparse = [recall_at_k(a, 5) == 1 for a, _ in pairs]
        dense = [recall_at_k(b, 5) == 1 for _, b in pairs]
        both = sum(s and d for s, d in zip(sparse, dense, strict=True))
        only_sparse = sum(s and not d for s, d in zip(sparse, dense, strict=True))
        only_dense = sum(d and not s for s, d in zip(sparse, dense, strict=True))
        lines.append(
            f"| {name} | {both} | {only_sparse} | {only_dense} | {len(pairs) - both - only_sparse - only_dense} |"
        )

    lines += ["", "## Latency per query (CPU)", "", "| Retrieval | Mean | P95 |", "| --- | --- | --- |"]
    for mode, values in timings.items():
        p95 = statistics.quantiles(values, n=20)[-1]
        lines.append(f"| {mode} | {_mean(values):.0f} ms | {p95:.0f} ms |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", choices=["test", "real", "dev"], default="test")
    parser.add_argument("--retrieval", action="store_true", help="retrieval and fusion evaluation (no LLM calls)")
    parser.add_argument("--tune", action="store_true", help="threshold sweep on the dev set (no LLM calls)")
    args = parser.parse_args()

    if args.tune:
        tune()
        return
    if args.retrieval:
        report = retrieval_eval()
        print(report)
        (EVAL_DIR / "retrieval_eval.md").write_text(report, encoding="utf-8")
        return

    service = make_service()
    questions = load_questions(str(EVAL_DIR), args.dataset)
    report = run_evaluation(service, questions, dataset=args.dataset)
    markdown = render_markdown(report)
    print(markdown)
    if args.dataset != "dev":
        target = EVAL_DIR / ("results.md" if args.dataset == "test" else "results_real.md")
        failed = sum(result.error is not None for result in report.results)
        if failed:
            # A run cut short by a provider quota says nothing about answer quality: keep the last good record.
            print(
                f"NOT saved: {failed} question(s) hit a provider error (usually a rate limit). {target.name} is unchanged."
            )
        else:
            target.write_text(markdown, encoding="utf-8")
            print(f"wrote {target}")


if __name__ == "__main__":
    main()
