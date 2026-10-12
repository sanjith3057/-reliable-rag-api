"""The RAG service: ingest, ask, and document management. Routes and the evaluator both call this."""

from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings
from app.domain import RetrievalTrace, ScoredChunk
from app.errors import AppError
from app.generation.excerpts import best_excerpts
from app.generation.llm_base import LLM, complete_with_retries
from app.generation.prompt import (
    DECOMPOSE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_answer_prompt,
    build_decompose_prompt,
)
from app.generation.validator import (
    NOT_AVAILABLE,
    parse_answer,
    parse_sub_questions,
    unsupported_numbers,
    validate_answer,
    wording_is_in_sources,
)
from app.ingestion.chunker import chunk_pages
from app.ingestion.hashing import doc_id_for
from app.ingestion.loaders import SUPPORTED_EXTENSIONS, load_document
from app.logging import get_logger, log_event, timed
from app.retrieval.embedder import Embedder
from app.retrieval.reranker import Reranker
from app.retrieval.retriever import RecursiveRetriever, Retriever
from app.retrieval.vector_store import VectorStore
from app.schemas import AskResponse, IngestResponse, Source
from app.security import sanitize_filename

logger = get_logger(__name__)


@dataclass
class AskOutcome:
    response: AskResponse
    retrieved: list[ScoredChunk] = field(default_factory=list)
    cited: list[ScoredChunk] = field(default_factory=list)
    trace: RetrievalTrace = field(default_factory=RetrievalTrace)
    timings: dict = field(default_factory=dict)


class RagService:
    def __init__(
        self,
        settings: Settings,
        store: VectorStore,
        embedder: Embedder,
        llm: LLM,
        reranker: Reranker | None = None,
    ):
        self.settings = settings
        self.store = store
        self.embedder = embedder
        self.llm = llm
        self.retriever = Retriever(
            store,
            embedder,
            hybrid=settings.enable_hybrid,
            reranker=reranker,
            raw_k=settings.raw_k,
            dense_weight=settings.hybrid_dense_weight,
            bm25_weight=settings.hybrid_bm25_weight,
        )
        self.recursive = RecursiveRetriever(
            self.retriever,
            self._decompose,
            gate=settings.similarity_threshold,
            sufficiency=settings.sufficiency_threshold,
            max_depth=settings.max_depth,
            max_sub_questions=settings.max_sub_questions,
        )

    # ── Ingestion ────────────────────────────────────────────────────────────
    def ingest(self, filename: str, data: bytes) -> IngestResponse:
        doc_name = sanitize_filename(filename)
        pages = load_document(doc_name, data, self.settings.max_file_bytes, self.settings.max_pdf_pages)
        doc_id = doc_id_for(data)
        chunks = chunk_pages(pages, doc_id, doc_name, self.settings.chunk_size, self.settings.chunk_overlap)
        embeddings = self.embedder.embed_documents([chunk.text for chunk in chunks])

        # Same bytes: replace the old chunks. Same name with new bytes: treat as a new version.
        status = "created"
        if self.store.delete_document(doc_id):
            status = "replaced"
        for existing in self.store.list_documents():
            if existing["doc_name"] == doc_name:
                self.store.delete_document(existing["doc_id"])
                status = "updated"
        self.store.add(chunks, embeddings)

        log_event(logger, "ingested", doc_id=doc_id, doc_name=doc_name, chunks=len(chunks), status=status)
        return IngestResponse(doc_id=doc_id, doc_name=doc_name, chunks=len(chunks), pages=len(pages), status=status)

    def ingest_directory(self, directory: str) -> list[IngestResponse]:
        folder = Path(directory)
        if not folder.is_dir():
            raise AppError("SAMPLE_DOCS_NOT_FOUND", f"Folder '{directory}' does not exist", 404)
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)
        return [self.ingest(path.name, path.read_bytes()) for path in files]

    def delete_document(self, doc_id: str) -> int:
        removed = self.store.delete_document(doc_id)
        if not removed:
            raise AppError("DOCUMENT_NOT_FOUND", f"No document with id '{doc_id}'", 404)
        return removed

    # ── Question answering ───────────────────────────────────────────────────
    def ask(self, question: str, top_k: int | None = None) -> AskOutcome:
        question = (question or "").strip()
        if not question:
            raise AppError("EMPTY_QUESTION", "The question must not be empty", 422)
        if len(question) > self.settings.max_question_chars:
            raise AppError(
                "QUESTION_TOO_LONG",
                f"The question must be at most {self.settings.max_question_chars} characters",
                422,
            )
        if self.store.count() == 0:
            raise AppError("NO_DOCUMENTS", "No documents have been ingested yet. Upload one first.", 409)

        k = top_k or self.settings.top_k
        timings: dict = {}

        with timed(timings, "retrieval_ms"):
            chunks, trace = self.recursive.retrieve(question, k)
        chunks = chunks[: self.settings.max_context_chunks]

        # Gate: if nothing is close enough, abstain without spending an LLM call.
        if trace.top_similarity < self.settings.similarity_threshold:
            return self._finish(question, _abstain("below_threshold"), chunks, trace, timings)

        if self.settings.include_neighbour_chunks:
            with timed(timings, "retrieval_ms"):
                chunks = self.retriever.with_neighbours(question, chunks, self.settings.max_context_chunks)

        verdict, labels = self._generate(question, chunks, timings)

        # Second chance. If the model found the evidence insufficient and the question has several
        # parts, retrieve each part on its own and ask once more. A question that asks for one fact
        # yields no sub-questions, so a true "not available" costs one small extra call and stays put.
        if (
            verdict.abstain_reason == "model_abstained"
            and self.settings.second_pass_on_abstain
            and not trace.sub_questions
        ):
            with timed(timings, "second_pass_ms"):
                wider = self._retrieve_by_parts(question, k, chunks, trace)
            if wider is not None:
                chunks = wider
                verdict, labels = self._generate(question, chunks, timings)

        if not verdict.answerable:
            return self._finish(question, _abstain(verdict.abstain_reason), chunks, trace, timings)

        with timed(timings, "excerpts_ms"):
            texts = [labels[label].chunk.text for label in verdict.citations]
            sources = [
                Source(
                    doc_name=labels[label].chunk.doc_name,
                    page=labels[label].chunk.page,
                    excerpt=excerpt,
                    score=round(labels[label].score, 4),
                )
                for label, excerpt in zip(
                    verdict.citations, best_excerpts(texts, question, verdict.answer, self.embedder), strict=True
                )
            ]
        cited = [labels[label] for label in verdict.citations]
        warnings = []
        cited_texts = [item.chunk.text for item in cited]
        if not wording_is_in_sources(verdict.answer, cited_texts):
            warnings.append(
                "The cited passages do not contain the wording of this answer. It may be inferred, not stated: "
                "check it against the evidence."
            )
        loose = unsupported_numbers(verdict.answer, question, cited_texts)
        if loose:
            warnings.append(
                f"These figures are not in the cited passages: {', '.join(loose)}. Check them against the evidence."
            )
        response = AskResponse(answer=verdict.answer, answerable=True, sources=sources, warnings=warnings)
        return self._finish(question, response, chunks, trace, timings, cited)

    def _generate(self, question: str, chunks: list[ScoredChunk], timings: dict):
        """One grounded-answer attempt: prompt, call, validate."""
        prompt, labels = build_answer_prompt(question, chunks)
        with timed(timings, "generation_ms"):
            payload = self.call_llm(SYSTEM_PROMPT, prompt, parse_answer)
        verdict = validate_answer(payload, set(labels))
        # Reasoning stays in the logs; the user only gets the answer and its sources.
        log_event(
            logger,
            "llm_reasoning",
            plan=payload.get("plan"),
            evidence_check=payload.get("evidence_check"),
            dropped_citations=verdict.dropped_citations,
        )
        return verdict, labels

    def _retrieve_by_parts(
        self, question: str, k: int, first_pass: list[ScoredChunk], trace: RetrievalTrace
    ) -> list[ScoredChunk] | None:
        """Split the question and retrieve each part. None means there was nothing to split."""
        sub_questions = self._decompose(question)[: self.settings.max_sub_questions]
        if len(sub_questions) < 2:
            return None
        trace.sub_questions.extend(sub_questions)
        trace.depth_reached = max(trace.depth_reached, 1)
        per_part = max(2, self.settings.max_context_chunks // (len(sub_questions) + 1))
        merged: dict[str, ScoredChunk] = {}
        # Each part's best passages go in first, so no part is crowded out by the others.
        for sub_question in sub_questions:
            trace.retrievals += 1
            for item in self.retriever.retrieve(sub_question, k)[:per_part]:
                merged.setdefault(item.chunk.chunk_id, item)
        for item in first_pass:
            merged.setdefault(item.chunk.chunk_id, item)
        return list(merged.values())[: self.settings.max_context_chunks]

    def _finish(self, question, response, chunks, trace, timings, cited=()) -> AskOutcome:
        log_event(
            logger,
            "ask",
            question=question[:200],
            answerable=response.answerable,
            abstain_reason=response.abstain_reason,
            top_similarity=round(trace.top_similarity, 4),
            depth=trace.depth_reached,
            sub_questions=trace.sub_questions,
            cited=[source.doc_name for source in response.sources],
            warnings=response.warnings,
            **timings,
        )
        return AskOutcome(response=response, retrieved=chunks, cited=list(cited), trace=trace, timings=timings)

    # ── LLM helpers ──────────────────────────────────────────────────────────
    def call_llm(self, system: str, user: str, parse):
        return complete_with_retries(
            self.llm,
            system,
            user,
            parse=parse,
            retries=self.settings.llm_max_retries,
            backoff_s=self.settings.llm_backoff_s,
            retry_after_cap_s=self.settings.llm_retry_after_cap_s,
        )

    def _decompose(self, question: str) -> list[str]:
        """Ask the LLM for sub-questions. If that fails, carry on with the evidence we already have."""
        try:
            return self.call_llm(DECOMPOSE_SYSTEM_PROMPT, build_decompose_prompt(question), parse_sub_questions)
        except AppError:
            log_event(logger, "decompose_failed")
            return []


def _abstain(reason: str | None) -> AskResponse:
    return AskResponse(answer=NOT_AVAILABLE, answerable=False, sources=[], abstain_reason=reason)
