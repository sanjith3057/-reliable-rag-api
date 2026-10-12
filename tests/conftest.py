"""Shared fixtures. Everything runs offline: FakeLLM, a hash embedder, and an in-memory vector store."""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.generation.providers import FakeLLM
from app.main import build_service, create_app
from app.retrieval.embedder import HashEmbedder

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DOCS = ROOT / "sample_docs"

PASSWORD_DOC = (
    b"Passwords must be at least 14 characters long. Passwords must be rotated every 180 days.\n\n"
    b"Multi-factor authentication is mandatory for all company accounts."
)


def make_settings(**overrides) -> Settings:
    values = {
        "llm_provider": "fake",
        "embedding_provider": "hash",
        "chroma_path": "",  # in-memory
        "collection_name": f"test-{uuid.uuid4().hex}",  # in-memory clients share state, so isolate by name
        "llm_backoff_s": 0.0,
        "eval_rate_limit_pause_s": 0.0,
        "similarity_threshold": 0.1,
        "sufficiency_threshold": 0.1,
        "enable_hybrid": False,  # retrieval upgrades are tested directly in test_retrieval.py
        "enable_reranker": False,
        "sample_docs_dir": str(SAMPLE_DOCS),
        "real_docs_dir": "",  # the 88-page PDF is for the live evaluation, not unit tests
        "eval_dir": str(ROOT / "eval"),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_client(llm: FakeLLM | None = None, **overrides) -> TestClient:
    app = create_app(make_settings(**overrides), llm=llm or FakeLLM(), embedder=HashEmbedder())
    return TestClient(app, raise_server_exceptions=False)


def make_service(llm: FakeLLM | None = None, **overrides):
    return build_service(make_settings(**overrides), llm=llm or FakeLLM(), embedder=HashEmbedder())


def upload(client: TestClient, name: str = "security.txt", data: bytes = PASSWORD_DOC):
    return client.post("/ingest", files={"file": (name, data)})


def assert_error(response, status: int, code: str) -> None:
    """Every error, whatever raised it, must have the one agreed shape."""
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["error"]["request_id"] == response.headers["x-request-id"]


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(llm) -> TestClient:
    return make_client(llm)
