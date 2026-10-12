from fastapi import APIRouter, File, Request, UploadFile

from app.errors import AppError
from app.evaluation.evaluator import load_questions, run_evaluation
from app.pipeline import RagService
from app.schemas import (
    AskRequest,
    AskResponse,
    DocumentList,
    ErrorResponse,
    EvalReport,
    EvalRequest,
    IngestResponse,
)

router = APIRouter(responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})


def _service(request: Request) -> RagService:
    return request.app.state.service


@router.get("/health", tags=["system"])
def health(request: Request) -> dict:
    service = _service(request)
    settings = service.settings
    return {
        "status": "ok",
        "documents": len(service.store.list_documents()),
        "chunks": service.store.count(),
        "llm": {"provider": service.llm.name, "model": service.llm.model},
        "embedding_model": service.embedder.name,
        "similarity_threshold": settings.similarity_threshold,
        "top_k": settings.top_k,
        "hybrid": settings.enable_hybrid,
        "reranker": settings.enable_reranker,
        "limits": {
            "max_file_mb": settings.max_file_mb,
            "max_question_chars": settings.max_question_chars,
            "max_eval_questions": settings.max_eval_questions,
        },
    }


@router.post("/ingest", status_code=201, tags=["documents"])
def ingest(request: Request, file: UploadFile = File(...)) -> IngestResponse:
    """Upload a PDF, TXT or MD file. Re-uploading the same content replaces its chunks."""
    service = _service(request)
    # Read one byte past the limit so an oversize upload is detected without buffering all of it.
    data = file.file.read(service.settings.max_file_bytes + 1)
    return service.ingest(file.filename or "", data)


@router.post("/ingest/samples", tags=["documents"])
def ingest_samples(request: Request) -> list[IngestResponse]:
    """Ingest the fictional documents bundled in sample_docs/ (the ones the eval set is written against)."""
    service = _service(request)
    ingested = service.ingest_directory(service.settings.sample_docs_dir)
    if service.settings.real_docs_dir:
        ingested += service.ingest_directory(service.settings.real_docs_dir)
    return ingested


@router.get("/documents", tags=["documents"])
def list_documents(request: Request) -> DocumentList:
    return DocumentList(documents=_service(request).store.list_documents())


@router.delete("/documents/{doc_id}", tags=["documents"])
def delete_document(doc_id: str, request: Request) -> dict:
    removed = _service(request).delete_document(doc_id)
    return {"deleted": doc_id, "chunks_removed": removed}


@router.post("/reset", tags=["documents"])
def reset(request: Request) -> dict:
    return {"status": "reset", "chunks_removed": _service(request).store.reset()}


@router.post("/ask", tags=["qa"])
def ask(body: AskRequest, request: Request) -> AskResponse:
    """Answer from the ingested documents only. `answerable` is false when the documents do not say."""
    return _service(request).ask(body.question, body.top_k).response


@router.post("/eval", tags=["evaluation"])
def evaluate(request: Request, body: EvalRequest | None = None) -> EvalReport:
    """Run an evaluation set through the live pipeline. With no body, runs eval/questions_test.json."""
    service = _service(request)
    settings = service.settings
    body = body or EvalRequest()

    if body.questions is None:
        questions, dataset = load_questions(settings.eval_dir, body.dataset), body.dataset
    else:
        questions, dataset = body.questions, "custom"
        if not questions:
            raise AppError("EMPTY_QUESTION_LIST", "Provide at least one question", 422)
        if len(questions) > settings.max_eval_questions:
            raise AppError("TOO_MANY_QUESTIONS", f"At most {settings.max_eval_questions} questions per run", 422)
    if service.store.count() == 0:
        raise AppError("NO_DOCUMENTS", "No documents have been ingested yet. Upload one first.", 409)

    # A question set is written against specific documents. Without them every answerable question
    # would be refused and the report would show zeros that say nothing about the system.
    library = {doc["doc_name"] for doc in service.store.list_documents()}
    missing = sorted({name for question in questions for name in question.expected_sources} - library)
    if missing:
        shown = ", ".join(missing[:5]) + (" and others" if len(missing) > 5 else "")
        raise AppError(
            "EVAL_DOCUMENTS_MISSING",
            f"This question set needs documents that are not in the library: {shown}. "
            "Load the sample docs (POST /ingest/samples) and run it again.",
            409,
        )

    report = run_evaluation(service, questions, top_k=body.top_k, dataset=dataset)
    request.app.state.latest_eval = report
    return report


@router.get("/eval/latest", tags=["evaluation"])
def latest_eval(request: Request) -> EvalReport:
    report = request.app.state.latest_eval
    if report is None:
        raise AppError("NO_EVAL_RUN", "No evaluation has been run since the server started", 404)
    return report
