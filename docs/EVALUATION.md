# Evaluation and tests

How the system was measured, what the numbers are, and how much to trust them.

- [In short](#in-short)
- [The question sets](#the-question-sets)
- [Results](#results)
- [Evaluate on your own documents](#evaluate-on-your-own-documents)
- [How these numbers changed, and why](#how-these-numbers-changed-and-why)
- [Retrieval and fusion evaluation (no LLM)](#retrieval-and-fusion-evaluation-no-llm)
- [Read these numbers with care](#read-these-numbers-with-care)
- [Reproduce](#reproduce)
- [Automated tests](#automated-tests)

## In short

| Question set | Result |
| --- | --- |
| 20 questions on made-up company documents | 20 / 20 (current configuration) |
| 18 questions on the 88-page GDPR regulation | 18 / 18 (one question is borderline; measured before the last two changes) |
| 10 generated questions on a document never used for tuning | 10 / 10 |
| 169 automated tests | 169 passed |

Every evaluation number comes from a live run: real retrieval, the real LLM, no mocks. The sets are
small and I wrote most of them, so this shows the pipeline works as designed. It is not a benchmark.

There are two kinds of check in this project, and they answer different questions:

| | Evaluation | Automated tests |
| --- | --- | --- |
| Question | Are the answers good? | Does the code do what it should? |
| Uses the real LLM | Yes | No, a scripted fake |
| Needs a key and quota | Yes | No |
| Time | Minutes | About 6 seconds |
| Run with | `python eval/run_eval.py` or the Evaluate tab | `pytest` |

## The question sets

All sets run against one mixed corpus of 584 chunks: the 8 short fictional documents plus an
88-page real PDF (the GDPR regulation, `real_docs/`).

| Set | Questions | Written against | Purpose |
| --- | --- | --- | --- |
| `questions_dev.json` | 21 | Both | Tuning only. Never reported as a result. |
| `questions_test.json` | 20 | Fictional documents | Grounding: the model cannot know these facts from training |
| `questions_real.json` | 18 | The GDPR PDF | Retrieval and abstention on long, dense, real text |

Four kinds of question are used:

| Kind | Example | What a pass looks like |
| --- | --- | --- |
| Answerable | "How many days of annual leave do employees get in 2025?" | Right fact, right document cited |
| Multi-evidence | A question whose answer needs two passages | Both facts, both sources |
| Unanswerable | "What does the Regulation say about blockchain?" | A refusal, with no citation |
| Distractor | A question where a similar document (the 2024 handbook, a different scanner) holds a wrong answer | The right document cited, not the near-miss |

The test set has 6 single-fact questions, 4 multi-evidence, 5 unanswerable (two near-topic traps,
one general knowledge) and 5 distractor questions (2024 vs 2025 handbook, Orbit A1 vs B2, and a year
and a product that do not exist). The real set has 10 single-fact, 3 multi-part and 5 unanswerable
questions.

## Results

Both runs: `bge-small-en-v1.5`, reranker on, top-k 5, 12 Oct 2026. The two columns were measured
with different settings, because the free quota ran out before the real set could be run again:

| | Test set | Real set |
| --- | --- | --- |
| Model | `qwen/qwen3.8-27b` (third in the failover chain) | `openai/gpt-oss-20b` (second) |
| Gate | 0.40 (current) | 0.50 (previous) |
| Neighbouring chunks | On (current) | Not yet built |

| Metric | Test set (fictional) | Real set (GDPR) | Definition |
| --- | --- | --- | --- |
| Questions passed | 20 / 20 | 18 / 18 | Every applicable check below passed |
| Retrieval hit@5 | 100% | 100% | The expected documents were retrieved and, on the real set, the supporting passage is inside a retrieved chunk |
| Abstention accuracy | 100% | 100% | Answered when it should, refused when it should |
| Citation correctness | 100% | 100% | At least one citation, and every citation is an expected document |
| Answer keyword accuracy | 100% | 100% | The answer contains the expected facts |
| Distractor resilience | 100% | n/a | Cited the right document and not the near-miss |
| Average latency | 13.2 s | 8.7 s | Dominated by rate-limit waits, see below |

Per-question tables: [`eval/results.md`](../eval/results.md) and
[`eval/results_real.md`](../eval/results_real.md).

**The test set column is the current configuration.** It was run after the gate was lowered and
neighbouring chunks were added, and it was answered by the weakest model in the chain.

**The real set column is not.** It predates both changes. What was re-checked for it: lowering the
gate changes the path of a question only if its best score is between 0.40 and 0.50, where it used
to be refused by the gate and is now passed to the LLM. That is one real-set question (r18), and it
was asked again and is still refused, now by the model. The effect of neighbouring chunks on the
real set has not been measured. Run `python eval/run_eval.py --dataset real` to measure it.

**One question is borderline.** r12 asks two things at once: how quickly a breach must be reported
and what the highest fine is. Those facts are on pages 52 and 83. In the run before this one it
failed: the two passages were not both retrieved, the model said the evidence was insufficient, and
the system refused. In this run the second pass found both and it passed, after 24 seconds. I count
that as a question the system can get right, not one it reliably does. Across every run, a failure
was always a wrong refusal or a provider error: no question in either set produced an unsupported
answer.

## Evaluate on your own documents

The sets above only show how the system does on documents I chose. To measure it on yours, upload
them and pick "My documents" in the Evaluate tab, or call the API:

```bash
curl -X POST http://localhost:8000/eval/generate -H "Content-Type: application/json" -d '{"n": 8}' > set.json
curl -X POST http://localhost:8000/eval -H "Content-Type: application/json" \
  -d "{\"questions\": $(jq .questions set.json), \"judge\": true}"
```

`/eval/generate` samples passages from the library and has the LLM write one question per passage,
with the answer keyword and a supporting quote. A draft is kept only if that quote and keyword
really are in the passage, so the gold labels cannot be invented. Three general-knowledge questions
are added that a grounded system must refuse. With `"judge": true`, a second LLM call grades each
answer for faithfulness (every claim is supported by the cited passages) and relevance.

Result on a document the system was never tuned on, a 5-page design document for an IT service
desk (10 chunks, not published here):

| Metric | Value |
| --- | --- |
| Questions passed | 10 / 10 (7 generated, 3 general-knowledge traps) |
| Retrieval hit@5 | 100% |
| Abstention accuracy | 100% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Faithfulness (LLM-judged) | 100% |
| Answer relevance (LLM-judged) | 100% |

That run was answered by `qwen/qwen3.8-27b`, the third model in the failover chain, because the
other two had used up their daily quota. Limits of this number:

- **Generated questions are easier than human ones.** Each comes from a single passage and tends to
  reuse its wording, so it does not test multi-part questions or paraphrase.
- **The judge is not independent.** It is the same model that wrote the answer, so it shares its
  blind spots. Treat judged scores as a check for obvious unsupported claims, not as ground truth.
- **The first run of this feature scored 25% on answer accuracy with every answer correct.** The
  generated keywords were too literal ("four" when the answer said "4", or a whole sentence). I
  fixed the generator and the matcher, not the answers; the judged faithfulness was 100% both times.
- **A correct answer can still miss the keyword.** On a one-page CV, the question "What performance
  increase did the agent achieve?" was answered "35 percentage points". The document says "from 65%
  to 100%", so the answer is right, but the keyword check failed it. The judge passed it.

## How these numbers changed, and why

I am including the history because the first version looked better than it was.

1. **First version: 20 / 20 on the test set.** Dense search only, gate at 0.60, tuned and tested
   only on the fictional documents.
2. **It then failed on a real document.** On a 28-chunk markdown file with tables, 3 of 4 ordinary
   questions were refused. Two causes: dense search did not rank the right passage in the top 5, and
   the gate blocked a valid question that scored 0.555.
3. **First run on the GDPR set: 11 / 18.** Six questions failed with `LLM_UNAVAILABLE` because the
   provider's rate limit outlasted the retries, and r12 failed as described above.
4. **Changes made in response:** reranker on, gate lowered to 0.50, second pass on abstention, model
   failover, fail-fast on long rate limits, and the evaluator now retries a rate-limited question
   after a pause so that a quota is not scored as a wrong answer. Each was checked on the dev set.
5. **Next run: 20 / 20 and 17 / 18**, with r12 still refused.
6. **One more change.** Testing failover on a real document showed the smaller model sometimes
   spent its output on hidden reasoning and returned no JSON. Setting its reasoning effort to low
   fixed that.
7. **Final run: 20 / 20 and 18 / 18.**

8. **A one-page form broke two more things.** A fictional medical intake form (13 questions asked
   by hand, not a scored set) showed that the evidence under correct answers was a section heading,
   and that the gate refused two questions the form plainly answers. The excerpt picker was
   rewritten to quote the lines that contain the answer, and the gate was lowered to 0.40. The
   reasoning is in [System design](SYSTEM_DESIGN.md#design-decisions-and-trade-offs).

After those changes, on the form:

| Question | Result |
| --- | --- |
| Why did she come in today? | Correct. Was refused by the gate before. |
| Does she smoke? | Correct ("No, she has never smoked"). Was refused by the gate before. |
| Preferred name; medications for chronic conditions | Correct, with the right lines quoted |
| Blood type; is her blood pressure under control? | Refused, correctly: the form does not say |
| Router password; refund policy; boiling point of water; capital of Australia | Refused, correctly |
| How old will she be in 2030? | "51", with two warnings that the figure is not in the cited text. A correct calculation, not a stated fact. |
| Is amoxicillin safe for her? | **Wrong kind of answer.** "Not safe, because she is allergic to penicillin." The form states the allergy; that amoxicillin is a penicillin is the model's own knowledge. |
| Emergency contact's number | **Wrong on one of three models.** `gpt-oss-20b` gave the right number. `qwen3.8-27b`, the last model in the failover chain, gave the patient's own number, which sits next to the word "Spouse" in the extracted text. |

The last two rows are failures that remain. Both are listed under
[limitations](SYSTEM_DESIGN.md#limitations).

9. **A 58-page project report showed an incomplete list.** "What is the tech stack used here" was
   answered from the first and last part of a section that spans four chunks. Chunks next to the
   retrieved ones are now added to the context, and sentences that the PDF wrapped over several
   lines are joined before they are quoted. After the change the answer also names OpenCV and
   TensorFlow; it still omits MediaPipe and MTCNN. Five other questions on that report (accuracy,
   guide, hardware, future scope, and one it cannot answer) came out right.

Steps 2 to 9 used information from outside the dev set, including the earlier real-set runs, so the
real-set score is not a clean held-out number. No change was made to target r12 specifically.

## Retrieval and fusion evaluation (no LLM)

Retrieval measured on its own, so a good or bad LLM cannot hide it. A chunk is relevant if it
contains the gold evidence text for the question. 584 chunks, 13 questions per set. Full output,
including nDCG@10, is in [`eval/retrieval_eval.md`](../eval/retrieval_eval.md).

| Term | Meaning |
| --- | --- |
| Recall@K | Share of the needed evidence found in the top K results |
| MRR | How near the top the first correct result is (1.0 = always first) |
| nDCG | Like recall, but correct results nearer the top count for more |
| BM25 | Classic keyword search |
| Dense | Search by meaning, using embeddings |
| Hybrid | BM25 and dense results merged |

Real document (GDPR):

| Retrieval | Recall@3 | Recall@5 | Recall@10 | MRR | nDCG@5 | Mean latency | P95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BM25 only | 0.54 | 0.54 | 0.54 | 0.49 | 0.48 | 2 ms | 3 ms |
| Dense only | 0.81 | 0.96 | 1.00 | 0.80 | 0.82 | 20 ms | 27 ms |
| Hybrid (BM25 + dense) | 0.81 | 0.81 | 0.96 | 0.79 | 0.76 | 23 ms | 29 ms |
| **Dense + reranker (default)** | 0.88 | 0.96 | 1.00 | 0.78 | 0.80 | 723 ms | 1199 ms |
| Hybrid + reranker | 0.88 | 0.96 | 0.96 | 0.78 | 0.80 | 2209 ms | 3659 ms |

On the fictional documents every method reaches Recall@5 of 1.00 and an MRR of 0.94 to 0.96, so
that set cannot tell them apart.

Complementarity, judged on full recall in the top 5: on the GDPR set both methods found the
evidence for 6 questions, only dense found it for 6, only BM25 for none, and neither for 1.

What this says:

- **Hybrid search is not worth it here.** BM25 never found evidence that dense search missed, and
  fusing it in pushed good dense results down (Recall@5 fell from 0.96 to 0.81). These questions
  are natural-language paraphrases, which is where keyword search is weakest. The sets contain no
  exact-token questions (error codes, IDs, function names), which is where BM25 should win, so this
  is a result about these questions, not about hybrid search in general.
- **The reranker's gain on these sets is small**: Recall@3 rises from 0.81 to 0.88, Recall@5 is
  unchanged, and MRR dips from 0.80 to 0.78. It costs about 0.7 s per question on CPU.
- **Why it is still on.** On a private markdown document with tables (10 questions, measured by
  hand) dense search put the evidence in the top 5 for 6 questions and the reranker for all 10, and
  on the dev set it took 12 of 13 to 13 of 13. That is weaker evidence than the table above,
  because I cannot publish that document. On the published sets alone, dense-only would be a
  defensible default and 0.7 s faster; `ENABLE_RERANKER=false` gives that.

## Read these numbers with care

- **Small sets, written by me.** 59 questions in total. This shows the pipeline works as designed
  on two kinds of document; it is not a benchmark.
- **The model already knows the GDPR.** A correct answer on the real set does not prove grounding
  by itself. The fictional set is what proves that. The real set shows retrieval, citation and
  refusal on long real text.
- **Latency is dominated by the free tier.** Groq allows 8,000 tokens per minute on this plan, so
  most questions waited for the limit to reset. Questions that did not wait took 1.1 to 3.0
  seconds, and questions stopped by the gate took about 0.5 seconds.
- **Model choice was forced.** The default model is `gpt-oss-120b`, but its 200,000-token daily
  quota was exhausted by earlier runs, so the numbers come from the two failover models (see the
  table under Results). An earlier test-set run on `gpt-oss-120b`, with the first version's
  settings, also scored 20 / 20. The current configuration has not been measured on `gpt-oss-120b`.
- **Answer accuracy is a keyword match**, which checks that the right number or name is present,
  not that the whole sentence is correct.

## Reproduce

```bash
python eval/run_eval.py                   # test set, writes eval/results.md
python eval/run_eval.py --dataset real    # real set, writes eval/results_real.md
python eval/run_eval.py --tune            # gate threshold sweep on the dev set (no LLM calls)
python eval/run_eval.py --retrieval       # retrieval and fusion evaluation (no LLM calls)
```

A full run costs roughly 30,000 to 50,000 tokens, so a 200,000-token daily quota covers only a
handful. The CLI and `POST /eval` call the same `run_evaluation` function. The CLI uses a clean
in-memory store, so it never touches the server's data. If a run is cut short by a provider error,
the CLI prints the result but does not overwrite the saved one.

## Automated tests

```bash
pytest          # 169 tests, about 6 seconds, no API key or network needed
ruff check .
```

Latest run: **169 passed, 0 failed**. The full output is recorded in
[`tests/RESULTS.md`](../tests/RESULTS.md). The same two commands run on every push
(`.github/workflows/ci.yml`).

| Area | What is tested |
| --- | --- |
| Chunking | Size limit, overlap, no lost text, metadata |
| Dedupe | Same file twice keeps one set of chunks; same name with new content replaces |
| Similarity | Distance converts correctly; a close match outscores a far one |
| Retrieval | A known question returns the expected chunk; PDF page numbers; BM25 fusion; reranking; chunks next to a hit are added, gaps between hits first |
| API | Ingest then ask end to end; list, delete, reset |
| Input failures | Unsupported type, empty file, corrupt PDF, oversize file, empty or too-long question |
| State failures | Asking with no documents |
| LLM failures | Timeout returns 503 after 2 retries; recovery on retry; malformed reply; bad key fails fast; exhausted quota fails fast with a clear message; failover to a second model |
| Provider client | Request shape, rate-limit and bad-JSON handling, timeouts, against a fake HTTP transport |
| Configuration | `.env.example` matches the code defaults and holds no secrets |
| Grounding | Gate skips the LLM; hallucinated citation stripped; uncited answer refused; abstention respected; a figure not in the cited passage is flagged |
| Excerpts | The quoted evidence contains the words of the answer; form values are quoted with their label, not a section heading; a second source shows what the first did not; a sentence a PDF wrapped over two lines is quoted whole |
| Prompt injection | Injected text stays inside its source block; an obedient model is still blocked |
| Recursion | Depth cap, sub-question cap, no duplicate chunks, fallback when the split fails; second pass after an abstention |
| Generated evaluation | Questions written from the library with verified gold labels; unverifiable drafts discarded; LLM judge; report survives a restart |
| Evaluation | All metric keys present; refuses to run when the documents a set needs are missing; abstention scored correctly; passage-level retrieval check; rate-limited questions retried; empty list and over-50 rejected |
| Errors | Every error response matches the one schema and carries the request ID |
| Security | Admin key and read-only key; client address behind a proxy; streamed upload cut off at the limit; API key accepted and rejected; 429 with `Retry-After`; limited requests never reach the LLM; size caps; headers; hostile filenames |
