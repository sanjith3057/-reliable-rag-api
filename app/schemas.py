"""Request and response models for the HTTP API."""

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class IngestResponse(BaseModel):
    doc_id: str
    doc_name: str
    chunks: int
    pages: int
    status: str = Field(description="created | replaced (same content re-ingested) | updated (same name, new content)")


class DocumentInfo(BaseModel):
    doc_id: str
    doc_name: str
    chunks: int
    pages: int
    ingested_at: str


class DocumentList(BaseModel):
    documents: list[DocumentInfo]


class AskRequest(BaseModel):
    question: str
    top_k: int | None = Field(default=None, ge=1, le=20)


class Source(BaseModel):
    doc_name: str
    page: int | None = None
    excerpt: str
    score: float = Field(description="Cosine similarity between the question and the cited chunk")


class AskResponse(BaseModel):
    answer: str
    answerable: bool
    sources: list[Source]
    abstain_reason: str | None = Field(
        default=None, description="below_threshold | model_abstained | no_valid_citations, when answerable is false"
    )


class EvalQuestion(BaseModel):
    id: str
    question: str
    type: str = "answerable"  # answerable | multi | unanswerable | distractor
    expected_answerable: bool
    expected_sources: list[str] = []
    expected_keywords: list[str] = []  # "a||b" means either a or b
    expected_evidence: list[str] = []  # text that must appear in a retrieved chunk (passage-level retrieval check)
    distractor_sources: list[str] = []


class EvalRequest(BaseModel):
    questions: list[EvalQuestion] | None = None
    dataset: str = Field(default="test", pattern="^(test|dev|real)$")
    top_k: int | None = Field(default=None, ge=1, le=20)


class EvalSummary(BaseModel):
    total: int
    passed: int
    retrieval_hit_at_k: float | None
    abstention_accuracy: float | None
    citation_correctness: float | None
    answer_keyword_accuracy: float | None
    distractor_resilience: float | None
    avg_latency_ms: float


class EvalResult(BaseModel):
    id: str
    type: str
    question: str
    passed: bool
    expected_answerable: bool
    answerable: bool | None
    retrieved: list[str]
    cited: list[str]
    retrieval_hit: bool | None
    citation_ok: bool | None
    keywords_ok: bool | None
    distractor_ok: bool | None
    latency_ms: float
    answer: str = ""
    error: str | None = None


class EvalReport(BaseModel):
    run_id: str
    dataset: str
    config: dict
    summary: EvalSummary
    results: list[EvalResult]
