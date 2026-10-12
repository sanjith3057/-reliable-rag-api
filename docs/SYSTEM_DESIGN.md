# System design

How Reliable RAG is built, and why. Written for developers and reviewers.
For a plain-language overview, start with the [README](../README.md).

- [Architecture](#architecture)
- [Components](#components)
- [Flow: adding a document](#flow-adding-a-document)
- [Flow: answering a question](#flow-answering-a-question)
- [Data model](#data-model)
- [API reference](#api-reference)
- [Settings](#settings)
- [Security](#security)
- [Design decisions and trade-offs](#design-decisions-and-trade-offs)
- [Limitations](#limitations)
- [Next steps](#next-steps)

## Architecture

![System architecture](images/architecture.svg)

One FastAPI process serves the web console and the API. Every request passes through the same
middleware (request ID, size cap, API key, rate limit) before it reaches a route. Routes call one
service object, `RagService`, which owns the two flows: ingest and ask.

Three things sit behind interfaces so they can be swapped without touching the pipeline:

| Interface | Default | Alternatives |
| --- | --- | --- |
| `LLM` | Groq (`openai/gpt-oss-120b`, with two fallback models) | OpenAI, Gemini, `FakeLLM` for tests |
| Embedder | `BAAI/bge-small-en-v1.5`, local, CPU | `HashEmbedder` for tests |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2`, local, CPU | Off (`ENABLE_RERANKER=false`) |

## Components

| Path | Responsibility |
| --- | --- |
| `app/main.py` | App factory, request middleware, model warm-up at start |
| `app/config.py` | Every setting, each overridable by an environment variable |
| `app/errors.py` | The single error format |
| `app/security.py` | API keys, rate limiter, size caps, input sanitising, security headers |
| `app/pipeline.py` | `RagService`: ingest and ask |
| `app/api/routes.py` | HTTP endpoints |
| `app/ingestion/` | File loaders, recursive chunker, content hashing |
| `app/retrieval/` | Embedder, vector store, retriever, reranker, optional BM25 |
| `app/generation/` | LLM interface, providers and failover, prompt, validator, excerpts |
| `app/evaluation/` | Evaluator, metrics, question generator, judge |
| `app/static/` | Web console: plain HTML, CSS and JavaScript, no build step |

## Flow: adding a document

![Adding a document](images/ingest-flow.svg)

| Step | Detail |
| --- | --- |
| Read | PDF through `pypdf` page by page; TXT and Markdown as UTF-8. A PDF page with no text layer (a scan) is rendered with `pypdfium2` and read by a local OCR model (RapidOCR). Parsed in memory, never written to disk. |
| Fingerprint | `doc_id` is the first 16 hex characters of the SHA-256 of the file bytes. Same bytes replace the same document. A different file under an existing name replaces the old version. |
| Split | Recursive chunker: 800 characters with 120 overlap, breaking at a paragraph, then a line, then a sentence, then a word. |
| Embed | Each chunk becomes a 384-dimension vector. |
| Store | Chunks, vectors and metadata go into one ChromaDB collection using cosine distance. |

## Flow: answering a question

![Answering a question](images/ask-flow.svg)

| Step | Detail |
| --- | --- |
| Overview route | A short question about the documents as a whole (`is_overview_question`: summarise, overview, key points, what is this document about) skips search and the gate. It gets 8 chunks taken at even intervals across the library (`OVERVIEW_CHUNKS`) plus the 3 best search hits. |
| Search | The question is embedded and the 20 nearest chunks are fetched (`RAW_K`). |
| Rerank | A cross-encoder re-scores the 20 and the best 5 are kept (`TOP_K`). |
| Gate | If the best cosine similarity is below 0.40, return "not available" with `abstain_reason: below_threshold`. No LLM call is made. |
| Split, if weak | If the best score is between 0.40 and 0.60, the question is split into up to 3 sub-questions and each is retrieved separately, to a depth of 2. |
| Neighbours | The context is filled up to 8 chunks (`MAX_CONTEXT_CHUNKS`) with chunks adjacent to the retrieved ones in the same document: first any chunks lying between two hits, then the chunk after each hit, then the chunk before. |
| Ask the LLM | Passages are placed in `<source>` blocks, strongest at the start and end. The model must return JSON: a plan, a per-source evidence check, the answer, and the source ids it used. |
| Second pass | If the model says the evidence is insufficient and the question has parts, split, retrieve and ask once more. |
| Validate | Citations not in the retrieved set are dropped, as are citations to sources the model itself marked as distractors. No citation left means "not available" (`no_valid_citations`). |
| Number check | Every figure in the answer must appear in a cited passage or the question; a miss adds a warning. |
| Wording check | If not one content word of the answer appears in the cited passages, a warning says the answer may be inferred, not stated. |
| Excerpts | From each cited chunk, the lines that contain the words of the answer are quoted. If none do, the sentences closest in meaning are used. No extra LLM call. |

If the LLM fails, it is retried twice with backoff, then the next model in the failover chain is
used. If every model is rate limited for longer than 30 seconds the request returns
`LLM_RATE_LIMITED` (503) with a `Retry-After` header.

## Data model

![What is stored](images/data-model.svg)

There is no relational database. Persistent state is:

**1. One ChromaDB collection, `documents`,** in the folder set by `CHROMA_PATH` (default
`chroma_data`). One record per chunk:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | `{doc_id}:{chunk_index}` |
| `document` | string | The chunk text |
| `embedding` | 384 floats | Vector from `bge-small-en-v1.5` |
| `metadata.doc_id` | string | First 16 hex characters of the file's SHA-256 |
| `metadata.doc_name` | string | Sanitised file name, shown in citations |
| `metadata.page` | integer | PDF page number; 0 means the format has no pages |
| `metadata.chunk_index` | integer | Position of the chunk inside the document |
| `metadata.ingested_at` | string | UTC timestamp, ISO 8601 |

A "document" is not stored separately. `GET /documents` groups the chunks by `doc_id` and counts
them. Deleting a document deletes its chunks.

**2. One file, `latest_eval.json`,** next to the collection. It holds the most recent evaluation
report (`run_id`, `dataset`, `config`, `summary`, `results[]`) so that it survives a restart.

**Not stored:** uploaded files, answers, API keys (environment only) and rate-limit counters
(memory only). The first 200 characters of each question are written to the server log.

## API reference

Interactive documentation is served at `/docs`.

| Method | Endpoint | Purpose | Needs admin key |
| --- | --- | --- | --- |
| GET | `/health` | Liveness and current configuration | Public |
| POST | `/ingest` | Upload a PDF, TXT or MD file | Yes |
| POST | `/ingest/samples` | Ingest the bundled sample and real documents | Yes |
| GET | `/documents` | List ingested documents | Read key is enough |
| DELETE | `/documents/{doc_id}` | Remove one document | Yes |
| POST | `/reset` | Clear the store | Yes |
| POST | `/ask` | Question in, grounded answer and sources out | Read key is enough |
| POST | `/eval` | Run an evaluation set, optionally with an LLM judge | Yes |
| POST | `/eval/generate` | Write an evaluation set from the library | Yes |
| GET | `/eval/latest` | The most recent evaluation report | Read key is enough |

The "needs admin key" column applies only when `API_KEY` is set. By default the API is open.

```bash
# Add a document
curl -F "file=@sample_docs/hr_policy_2025.md" http://localhost:8000/ingest

# Ask something the documents answer
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "How many days of annual leave do employees get in 2025?"}'
```

```json
{
  "answer": "24 days",
  "answerable": true,
  "sources": [
    {
      "doc_name": "hr_policy_2025.md",
      "page": null,
      "excerpt": "In 2025, full-time employees are entitled to 24 days of paid annual leave per calendar year.",
      "score": 0.8213
    }
  ],
  "abstain_reason": null,
  "warnings": []
}
```

```bash
# Ask something they do not answer
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "Who is the CEO of Lumenfold Systems?"}'
```

```json
{
  "answer": "The information is not available in the provided documents.",
  "answerable": false,
  "sources": [],
  "abstain_reason": "model_abstained",
  "warnings": []
}
```

| `abstain_reason` | Meaning |
| --- | --- |
| `below_threshold` | Nothing relevant was retrieved. No LLM call was made. |
| `model_abstained` | Related passages were found but none state the answer |
| `no_valid_citations` | The model answered but could not tie the answer to a retrieved passage |

Every error has one shape:

```json
{"error": {"code": "UNSUPPORTED_FILE_TYPE", "message": "Only PDF, TXT, MD are accepted", "request_id": "3f9c1a2b7d10"}}
```

| Status | Codes |
| --- | --- |
| 401 / 403 | `UNAUTHORIZED`, `FORBIDDEN` |
| 404 | `NOT_FOUND`, `DOCUMENT_NOT_FOUND`, `NO_EVAL_RUN`, `EVAL_SET_NOT_FOUND`, `SAMPLE_DOCS_NOT_FOUND` |
| 409 | `NO_DOCUMENTS`, `EVAL_DOCUMENTS_MISSING` |
| 413 | `FILE_TOO_LARGE`, `REQUEST_TOO_LARGE` |
| 415 | `UNSUPPORTED_FILE_TYPE` |
| 422 | `EMPTY_FILE`, `NO_TEXT_EXTRACTED`, `UNREADABLE_FILE`, `TOO_MANY_PAGES`, `TOO_MANY_SCANNED_PAGES`, `OCR_UNAVAILABLE`, `EMPTY_QUESTION`, `QUESTION_TOO_LONG`, `EMPTY_QUESTION_LIST`, `TOO_MANY_QUESTIONS` |
| 429 | `RATE_LIMITED` (with `Retry-After`) |
| 503 | `LLM_RATE_LIMITED` (with `Retry-After`), `LLM_UNAVAILABLE` |

## Settings

Every setting lives in `app/config.py` and can be set in `.env` or as an environment variable.
The most useful ones:

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_PROVIDER` | `groq` | `groq`, `openai`, `gemini` or `fake` (no key needed) |
| `GROQ_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` | empty | The key for the chosen provider |
| `LLM_MODEL` | provider default | Groq: `openai/gpt-oss-120b` |
| `LLM_FALLBACK_MODEL` | provider default | Comma-separated models tried while the main one is rate limited |
| `LLM_TIMEOUT_S` / `LLM_MAX_RETRIES` | 30 / 2 | Per-call timeout and retries |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model |
| `TOP_K` | 5 | Passages kept after search and reranking |
| `MAX_CONTEXT_CHUNKS` | 8 | Most passages given to the LLM, neighbours included |
| `INCLUDE_NEIGHBOUR_CHUNKS` | true | Add the chunks next to the retrieved ones |
| `OVERVIEW_CHUNKS` | 8 | Chunks sampled across the library for a summary question; 0 turns the route off |
| `SIMILARITY_THRESHOLD` | 0.40 | The gate: below this, no LLM call |
| `ENABLE_RERANKER` | true | Cross-encoder reranking of the top 20 |
| `ENABLE_HYBRID` | false | Add BM25 keyword search to dense search |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 800 / 120 | Characters per chunk and overlap |
| `CHROMA_PATH` | `chroma_data` | Where the vector store lives; empty means in memory |
| `API_KEY` | empty | Admin key. Empty leaves the API open. |
| `READ_API_KEY` | empty | Optional key that can only ask and list |
| `TRUSTED_PROXY_HOPS` | 0 | Reverse proxies in front of the app |
| `RATE_LIMIT_ASK_PER_MIN` | 30 | Also `_INGEST_` 20, `_EVAL_` 3, `_DEFAULT_` 120 |
| `MAX_FILE_MB` / `MAX_PDF_PAGES` | 10 / 500 | Upload limits |
| `ENABLE_OCR` / `MAX_OCR_PAGES` | true / 25 | Read scanned PDF pages with OCR, and how many per file |

## Security

| Control | How |
| --- | --- |
| API keys | Set `API_KEY` and every data endpoint requires a matching `X-API-Key` header (401 otherwise). An optional `READ_API_KEY` can only ask questions and list documents; uploading, deleting, resetting and evaluating return 403 without the admin key. Comparison is constant-time. The UI shell, `/health` and `/docs` stay public. Both are empty by default, so local use needs no setup. |
| Rate limiting | Sliding window per client address, with a separate budget for each kind of work: 30 questions, 20 uploads and 3 evaluations per minute, 120 for everything else. Over the limit returns 429 with a `Retry-After` header, before any LLM call is made. `X-Forwarded-For` is ignored unless `TRUSTED_PROXY_HOPS` says how many proxies are yours, and then it is read from the right, so a caller cannot forge an address to dodge the limit. |
| Request size | 10 MB for uploads, 256 KB for JSON. A body is refused from its declared length before it is read, and the bytes are also counted as they arrive, so a streamed upload with no `Content-Length` is cut off at the limit too. PDFs are capped at 500 pages. |
| Upload handling | Only `.pdf`, `.txt`, `.md`. Filenames are reduced to a safe display name (no paths, no markup), because the name is stored, shown in the UI and written into the prompt. Files are parsed in memory and never written to disk or executed. |
| Prompt injection | Document text sits inside `<source>` blocks it cannot close or forge; the system prompt declares sources to be data. An answer that carries no valid citation is discarded, so an obedient model still cannot leak an injected reply. `sample_docs/it_notice.txt` contains an "ignore all previous instructions" attack and is part of the evaluation corpus. |
| Browser | `Content-Security-Policy` with no inline scripts or styles, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`. All document and model text is rendered with `textContent`. No CORS headers are sent, so other sites cannot call the API from a browser. |
| Secrets | Keys come from environment variables only, `.env` is git-ignored, and keys never appear in responses or logs. Unexpected errors return a generic 500; details go to the server log with the request ID. |
| Container | Runs as an unprivileged user. |

```bash
# With API_KEY set
curl -H "X-API-Key: $API_KEY" http://localhost:8000/documents
```

## Design decisions and trade-offs

**Distance is converted to similarity in one place.** ChromaDB returns cosine *distance*, where
smaller is better. Comparing that against a "minimum similarity" threshold inverts the gate: the
system either refuses everything or answers everything. `vector_store.distance_to_similarity` does
the conversion once, and `tests/test_similarity.py` checks it against vectors with a known cosine.

**A loose retrieval gate before the LLM.** If the best passage scores below 0.40, the API returns
"not available" without calling the LLM. This value was lowered twice, each time because a new
kind of document proved the last one wrong:

| Gate | Why it looked right | What broke it |
| --- | --- | --- |
| 0.60 | The lowest answerable question on the sample documents scores 0.66 | On a real markdown document, valid questions scored 0.55 to 0.66 and were refused |
| 0.50 | Off-topic questions on the evaluation corpus score 0.47 to 0.49 | On a one-page medical form, "Why did she come in today?" scored 0.447 and "Does she smoke?" 0.458, and both were refused. The form answers both. |
| 0.40 | Current value | Not yet broken. Nothing guarantees it will not be. |

The form showed the real problem. On that document an off-topic question ("What is the refund
policy for online orders?", 0.483) scores *higher* than two questions the form answers. No
threshold can separate them, because the score measures how alike the wording is, and a short
conversational question shares little wording with a terse form.

So the gate is now only a cost saver for questions that are nowhere near the documents (on the
form, "What is the capital of Australia?" scores 0.37). The decision to refuse belongs to the
model's own abstention and the validator. I checked that directly: every evaluation question that
the old gate stopped and the new one lets through (one in the test set, one in the real set, two
in the dev set) is still refused, now by the model. The cost is one LLM call for each such question.

**A reranker after dense search.** The 20 nearest chunks are re-scored by a small cross-encoder and
the best 5 are kept. This was off in my first version because it made no difference on the sample
documents. On a real markdown document with tables it was the difference between finding the right
passage for 6 of 10 questions and 10 of 10. On the published sets its gain is small (see the
[retrieval evaluation](EVALUATION.md#retrieval-and-fusion-evaluation-no-llm)), and it adds about
0.7 s per question on CPU, so this default is a judgement call.

**A validator after the LLM.** The model must return JSON with the source ids it used. Citations
that do not match a retrieved passage are dropped, as are citations to passages the model itself
labelled a distractor. An answer with no surviving citation is replaced by "not available". This is
what makes a hallucinated source impossible to return, whatever the model does.

**Fictional sample documents.** The sample corpus describes a made-up company. The model cannot
know these facts from training, so a correct answer proves retrieval worked, and a refusal on "What
is the capital of Australia?" proves the model is not answering from memory.

**A PrismRAG-inspired prompt, not PrismRAG.** The prompt asks for a plan, then a per-source evidence
check that flags distractors, then the answer. That shape is borrowed from the PrismRAG paper. The
paper's actual method is fine-tuning on distractor-heavy data, which this project does not do.
Grounding here is enforced in code after the model answers (the gate, the citation validator, the
number check), so it holds for any model behind the API and can be tested without one.

**Position-aware context.** The strongest passages go at the start and end of the context and the
weakest in the middle, because models attend least to the middle of a long prompt.

**Local embeddings.** `bge-small-en-v1.5` runs on CPU, costs nothing per call, and keeps document
text on the machine. Tests swap in a deterministic hash embedder so CI needs no model download.

**One HTTP client for three providers.** Groq, OpenAI and Gemini all accept the OpenAI
chat-completions format, so `OpenAICompatibleLLM` covers them with a different base URL and key.
`LLM_PROVIDER` selects one. `FakeLLM` implements the same interface for tests.

**Multi-part questions get a second pass.** Two triggers split a question into sub-questions and
retrieve each part separately. Before answering: when the best score is weak (between 0.40 and
0.60), to a maximum depth of 2. After answering: when the model reports that the evidence is
insufficient, once. A question that asks for a single fact yields no sub-questions, so a genuine
"not available" costs one small extra call and stays a refusal. If the split fails, the pipeline
carries on with the evidence it already has.

**Failover between models.** Free tiers cap tokens per minute and per day for each model
separately. When the main model is rate limited, calls go to the next model in a chain until the
limit resets (`LLM_FALLBACK_MODEL`, three models by default on Groq). If the provider says the wait
is longer than 30 seconds, the request fails at once with `LLM_RATE_LIMITED` and a `Retry-After`
header, because retrying cannot help. I found this the hard way: my own evaluation runs used up a
200,000-token daily quota and the first version just waited and returned a vague 503.

**A number check on every answer.** An invented figure is the most common and most damaging kind of
hallucination, and it is cheap to catch: every number in an answer must appear in a cited passage
or in the question. A miss is reported as a warning, not a refusal, because a correct answer can
contain a figure the model worked out, such as a difference between two values.

**Neighbouring chunks are added to the context.** A 58-page project report showed why. Its
"Software Specification" section is one long paragraph that spans four chunks. Asked "what is the
tech stack used here", search returned the first and the last of them and two bibliography entries,
so the answer listed Windows, Python, Pygame, NumPy and Pandas and left out OpenCV and TensorFlow,
which are in the middle. Now the chunks between two hits, and the ones just after and before each
hit, fill the context up to 8. The gap between the two best-ranked hits is filled first: my first
version filled gaps in page order and spent its three free slots on the wrong side of the section.
The same question now returns the full list, including OpenCV, TensorFlow, MediaPipe and MTCNN. The
cost is up to three more chunks of tokens per question.

**Answer length follows the question.** The prompt first said "Keep the answer short", which
turned "How does the system detect drowsiness?" into one clipped line. It now asks for one short
sentence for a single fact, and a complete answer (several sentences, or lines starting with a
dash) for a list, an explanation or a summary.

**A separate route for whole-document questions.** "Summarise this document" is not similar to
any single passage, so search returns little and the gate used to refuse it. A short question that
matches a small list of overview phrasings now skips search: it reads 8 chunks taken at even
intervals across the library, plus the 3 best search hits, and the citation rules still apply. The
phrase list is a heuristic and will miss unusual wordings, which then go through search as before.

**Excerpts that contain the answer, without another LLM call.** The cited chunk is split into lines
and sentences, and the ones that together contain the most words of the answer are quoted. When a
second chunk is cited, it shows the part of the answer the first did not. If no line shares a word
with the answer (a paraphrase), the sentences closest in meaning are used instead. The first version
ranked only by similarity to the question and skipped lines without closing punctuation. On a
filled-in PDF form that showed a section heading ("EMERGENCY CONTACT 3.") under a correct answer,
because form values such as a name or a phone number are bare lines. The answer was grounded but
the evidence on screen did not show it. Lines that a PDF wrapped in the middle of a sentence are
joined again first, so the excerpt is a whole sentence and not a fragment of one.

**Lazy imports.** ChromaDB, pypdf, the BM25 library, the HTTP client and sentence-transformers are
imported inside the functions that first need them, not at module load. Importing the app dropped
from about 1.7 s to 0.8 s on my machine, which speeds up tests, the CLI and worker start-up, and
features that are switched off (BM25) never load their libraries at all. The models themselves are
still loaded at server start, on purpose, so the first question is not slow. Python 3.15 adds a
`lazy import` statement (PEP 810) that does this more cleanly, and I tried it: the statement works
on 3.15, but `onnxruntime`, which ChromaDB requires, has no Python 3.15 wheels yet, so the project
cannot run there today. Function-level imports give the same effect on Python 3.12 to 3.14.

**A hand-written rate limiter.** About 30 lines with no dependency, which is enough for one
process. The trade-off is that each worker or replica keeps its own count; a multi-instance
deployment would move the counters to Redis.

**BM25 fusion is implemented but off.** `ENABLE_HYBRID` adds keyword search fused with dense
search. In the retrieval evaluation it never found evidence that dense search missed and it lowered
Recall@5, so it is not a default.

**No fine-tuning.** A fine-tuned model would only be less likely to invent a source. The validator
makes an invented source impossible to return, for any model, and it needs no GPU or training data.

## Limitations

What this does not do, grouped by where it would bite.

**Evaluation**

- **The bundled sets are small and I wrote them.** 59 questions. They show the pipeline works as
  designed on two kinds of document; they are not a benchmark.
- **Generated sets are easier than human-written ones**, and the LLM judge is the same model that
  answered. Both are useful for testing your own documents and both flatter the system somewhat.
- **Evaluation runs inside the request.** A full run holds the HTTP connection open for a minute or
  more. A job queue would be the fix.

**Retrieval and answers**

- **Fixed-size chunks.** A table or long list can be split across chunks. Adding neighbouring
  chunks helps, but an answer that needs a whole long section can still miss items.
- **Forms lose their layout.** Text extracted from a PDF form comes out as bare lines, and a value
  can land far from its label, or in a different chunk. The model has to match values to labels by
  itself, and a weaker model gets it wrong: on a test form, the last model in the failover chain
  returned the patient's phone number as the emergency contact's. The answer cited a real passage,
  so nothing in the code caught it.
- **The model can still reason from its own knowledge on top of a cited fact.** Asked "Is
  amoxicillin safe for her?" about a form that records a penicillin allergy, it answered "not
  safe". The allergy is in the form; that amoxicillin is a penicillin is not. A stricter prompt
  rule did not change this in a quick test, so it was not kept. The wording check only
  catches an answer that shares no word at all with its evidence.
- **The gate cannot tell "off-topic" from "worded differently".** See the decision on the gate.
  Below 0.40 a question is refused without asking the model, and a valid but oddly worded question
  could still fall there.
- **Excerpts are chosen by shared words.** A paraphrased answer falls back to the closest sentence,
  which is weaker evidence than a line containing the answer itself.
- **Multi-part questions across distant sections can still fail**, as r12 did in one of two runs.
- **A summary is built from a sample.** "Summarise this document" reads 8 chunks spread across the
  library plus 3 search hits. On a long document, or a library of many documents, most of the text
  is never seen, and a summary request worded unusually is not recognised as one.
- **The number check is a warning and only covers figures.** It flags a number that is not in the
  cited passages, including one the model correctly worked out. An invented claim with no number in
  it is caught only by the citation rules and, in evaluation, by the judge.
- **OCR is basic.** Scanned pages are read by a small local model: fine for clean print, poor for handwriting, skewed photos and tables. Recognised text is not corrected, so a misread word cannot be found by search. A scan is limited to 25 pages because each page takes a few seconds on a CPU.
- **English only**, and the gate threshold belongs to this embedding model. A different model needs
  `python eval/run_eval.py --tune` run again.
- **No streaming.** The answer arrives whole, because it has to be validated before any of it is shown.

**Operations and security**

- **Free-tier quotas are finite.** Three models in a failover chain stretch a Groq free key a long
  way, but each still stops after about 200,000 tokens a day.
- **The reranker costs about 0.7 s per question on CPU** and adds a second model to the image.
- **Two keys, not user accounts.** An admin key and a read-only key cover "who may change things",
  but there are no per-user documents: everyone with a key sees the same library.
- **Rate limits are per process.** They reset on restart and are not shared between replicas; that
  needs a shared store such as Redis.
- **No TLS.** The server speaks plain HTTP and expects a reverse proxy to terminate HTTPS. Set
  `TRUSTED_PROXY_HOPS` when you add one, or every request will appear to come from the proxy.
- **Prompt-injection defences reduce risk, they do not remove it.** A model can still be misled by
  document text into a wrong answer that cites that text.

## Next steps

- A larger evaluation corpus written by someone else, with an independent judge model.
- Structure-aware chunking that keeps tables whole and carries section headings into each chunk.
- A map-reduce path for whole-document questions such as summaries.
- Background jobs for evaluation and large uploads, with progress reporting.
- Per-user libraries and accounts in place of shared keys.
- Follow-up questions. Each question is answered on its own today. The next step is to rewrite a
  follow-up ("and for contractors?") into a full question using the previous turn, then search as
  usual, so the answer is still cited. A memory library such as mem0 was considered and left out:
  remembered chat would be a second, uncited source next to the documents.
- Better OCR for scans: straighten skewed pages, keep table layout, and handle handwriting.
