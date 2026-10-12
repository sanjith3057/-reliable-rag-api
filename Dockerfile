FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache \
    CHROMA_PATH=/data/chroma

WORKDIR /srv

# OpenCV, used by the OCR model for scanned PDFs, needs these two system libraries.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch first: the default Linux wheel bundles CUDA and is several GB larger.
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake both models into the image so the container starts offline and fast.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ARG RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN python -c "from sentence_transformers import CrossEncoder, SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}'); CrossEncoder('${RERANKER_MODEL}')"

COPY app ./app
COPY eval ./eval
COPY sample_docs ./sample_docs
COPY real_docs ./real_docs

# The model is already in the image; never reach for the network at runtime.
ENV HF_HUB_OFFLINE=1

# Run as an unprivileged user. /data is created first so the volume inherits its ownership.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /opt/hf-cache
USER appuser

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
