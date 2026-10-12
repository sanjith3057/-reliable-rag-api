from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunables in one place. Every field can be overridden by an env var of the same name."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    # LLM
    llm_provider: str = "groq"  # groq | gemini | openai | fake
    llm_model: str = ""  # empty = the provider's default model
    # Tried in order while the main model is rate limited; comma-separated. Empty = the provider's defaults.
    llm_fallback_model: str = ""
    llm_reasoning_effort: str = "low"  # only sent to models that accept it (gpt-oss); empty = model default
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    llm_timeout_s: float = 30.0
    llm_max_retries: int = 2
    llm_backoff_s: float = 1.0
    llm_retry_after_cap_s: float = 30.0  # longest we will wait when the provider says "slow down"

    # Evaluation only: a question that fails because the provider is rate limiting is retried after a
    # pause, so a free-tier quota does not get scored as a wrong answer.
    eval_rate_limit_retries: int = 3
    eval_rate_limit_pause_s: float = 30.0

    # Embeddings
    embedding_provider: str = "sentence-transformers"  # sentence-transformers | hash
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Vector store. An empty path means in-memory (used by tests and the eval CLI).
    chroma_path: str = "chroma_data"
    collection_name: str = "documents"

    # Chunking
    chunk_size: int = 800
    chunk_overlap: int = 120

    # Retrieval
    top_k: int = 5
    # The abstention gate. Deliberately loose: it only stops clearly off-topic questions, because valid
    # questions on real documents score as low as 0.55. Near-topic traps are left to the model and validator.
    similarity_threshold: float = 0.50
    sufficiency_threshold: float = 0.60  # at or above this, first-pass evidence is enough (no decomposition)
    max_depth: int = 2
    max_sub_questions: int = 3
    max_context_chunks: int = 8
    second_pass_on_abstain: bool = True  # if the model abstains, split the question and try once more

    # Second-stage retrieval. The reranker is on because dense search alone misses passages in real
    # documents (see the ablation in the README); BM25 fusion is available but showed no extra gain.
    enable_reranker: bool = True
    enable_hybrid: bool = False
    hybrid_dense_weight: float = 0.65
    hybrid_bm25_weight: float = 0.35
    raw_k: int = 20  # candidates fetched before fusion / reranking
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Limits
    max_file_mb: int = 10
    max_pdf_pages: int = 500
    max_question_chars: int = 1000
    max_eval_questions: int = 50
    max_json_kb: int = 256  # request body cap for everything that is not a file upload

    # Security. An empty API key leaves the API open (fine for local use); set one before exposing it.
    api_key: str = ""  # full access: upload, delete, reset, evaluate, ask
    read_api_key: str = ""  # optional second key that can only ask questions and list documents
    # How many reverse proxies sit in front of the app. 0 = none, so X-Forwarded-For is ignored
    # (any caller can forge it). Set to 1 behind a single proxy such as nginx or a cloud load balancer.
    trusted_proxy_hops: int = 0
    rate_limit_enabled: bool = True
    rate_limit_ask_per_min: int = 30
    rate_limit_ingest_per_min: int = 20
    rate_limit_eval_per_min: int = 3
    rate_limit_default_per_min: int = 120

    # Paths
    sample_docs_dir: str = "sample_docs"
    real_docs_dir: str = "real_docs"  # a long real PDF, so evaluation is not only on tidy fictional text
    eval_dir: str = "eval"

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
