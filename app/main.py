import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import Settings, get_settings
from app.errors import AppError, error_response, register_error_handlers
from app.generation.llm_base import LLM
from app.generation.providers import build_llm
from app.logging import configure_logging, get_logger, log_event, set_request_id
from app.pipeline import RagService
from app.retrieval.embedder import Embedder, build_embedder
from app.retrieval.reranker import CrossEncoderReranker, Reranker
from app.retrieval.vector_store import VectorStore
from app.security import (
    SECURITY_HEADERS,
    UI_CONTENT_SECURITY_POLICY,
    RateLimiter,
    guard_request,
    sanitize_request_id,
)

STATIC_DIR = Path(__file__).parent / "static"
logger = get_logger(__name__)


def build_service(
    settings: Settings,
    *,
    llm: LLM | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> RagService:
    if reranker is None and settings.enable_reranker:
        reranker = CrossEncoderReranker(settings.reranker_model)
    return RagService(
        settings=settings,
        store=VectorStore(settings.chroma_path, settings.collection_name),
        embedder=embedder or build_embedder(settings.embedding_provider, settings.embedding_model),
        llm=llm or build_llm(settings),
        reranker=reranker,
    )


def create_app(
    settings: Settings | None = None,
    *,
    llm: LLM | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> FastAPI:
    """App factory. Tests pass a FakeLLM and a hash embedder; production reads everything from the environment."""
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load the models before the first request instead of during it.
        service = app.state.service
        for component in (service.embedder, service.retriever.reranker):
            warm_up = getattr(component, "warm_up", None)
            if warm_up:
                warm_up()
        yield

    app = FastAPI(
        title="Reliable RAG API",
        description="Answers questions from your documents, cites its evidence, and says so when it cannot.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.service = build_service(settings, llm=llm, embedder=embedder, reranker=reranker)
    app.state.latest_eval = None
    app.state.rate_limiter = RateLimiter()

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = sanitize_request_id(request.headers.get("x-request-id")) or uuid.uuid4().hex[:12]
        set_request_id(request_id)
        path = request.url.path
        try:
            guard_request(request, settings, app.state.rate_limiter)
            response = await call_next(request)
        except AppError as exc:
            log_event(logger, "request_rejected", code=exc.code, status=exc.status_code, path=path)
            response = error_response(exc.code, exc.message, exc.status_code, exc.headers)
        except Exception:
            # Caught here, not in an exception handler, so the 500 still carries the request ID header.
            logger.exception("unhandled_error")
            response = error_response("INTERNAL_ERROR", "Something went wrong on our side.", 500)
        response.headers["x-request-id"] = request_id
        response.headers.update(SECURITY_HEADERS)
        if path == "/" or path.startswith("/static/"):
            response.headers["Content-Security-Policy"] = UI_CONTENT_SECURITY_POLICY
        if not request.url.path.startswith("/static"):
            log_event(logger, "request", method=request.method, path=request.url.path, status=response.status_code)
        return response

    register_error_handlers(app)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


def app() -> FastAPI:
    """Entry point for `uvicorn app.main:app --factory`."""
    return create_app()
