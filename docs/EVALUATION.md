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
| 20 questions on made-up company documents | 20 / 20 |
| 18 questions on the 88-page GDPR regulation | 18 / 18 |
| 10 generated questions on a document never used for tuning | 10 / 10 |
| 18 questions on a filled-in form and a handwritten scan | 17 / 18; the miss is a handwritten date the OCR misread |
| 21 questions on a 48-page project report | 18 of 21 ran and all 18 passed; the last 3 were stopped by the provider's daily limit, so the run is not saved |
| 194 automated tests | 194 passed |

Every evaluation number comes from a live run: real retrieval, the real LLM, no mocks. The sets are
small and I wrote most of them, so this shows the pipeline works as designed. It is not a benchmark.

There are two kinds of check in this project, and they answer different questions:

| | Evaluation | Automated tests |
| --- | --- | --- |
| Question | Are the answers good? | Does the code do what it should? |
| Uses the real LLM | Yes | No, a scripted fake |
| Needs a key and quota | Yes | No |
| Time | Minutes | About half a minute |
| Run with | `python eval/run_eval.py` or the Evaluate tab | `pytest` |

## The question sets

All sets run against one mixed corpus of 684 chunks from 12 documents: the 8 short fictional
documents, an 88-page real PDF (the GDPR regulation), a 48-page student project report, a filled-in
medical intake form (fictional) and a handwritten page read with OCR. The last four are in
`real_docs/`.

The test, real and forms results below were measured when the corpus was 588 chunks from 11
documents, before the project report was added. They have not been re-run on the larger corpus:
the daily quota was spent.

| Set | Questions | Written against | Purpose |
| --- | --- | --- | --- |
| `questions_dev.json` | 21 | Both | Tuning only. Never reported as a result. |
| `questions_test.json` | 20 | Fictional documents | Grounding: the model cannot know these facts from training |
| `questions_real.json` | 18 | The GDPR PDF | Retrieval and abstention on long, dense, real text |
| `questions_forms.json` | 18 | A filled-in form and a handwritten scan | Documents that are not prose: label and value pairs, and text read with OCR |
| `questions_report.json` | 21 | A 48-page project report | Five difficulty levels on one long document someone else might upload |

Every reported question also carries a level from 1 to 5, and
[`eval/QUESTION_BANK.md`](../eval/QUESTION_BANK.md) lists them by level and by document format
with the pass mark from the last saved run.

| Level | Kind of question |
| --- | --- |
| 1 | One fact stated in one place |
| 2 | A list or several facts from one passage |
| 3 | Facts from different passages or documents |
| 4 | A similar but wrong value sits close by |
| 5 | Must be refused |

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

All three runs: 13 Oct 2026, `bge-small-en-v1.5`, reranker on, top-k 5, gate 0.40, neighbouring
chunks on, the longer-answer prompt, on the 588-chunk corpus of that morning. The test and real sets ran on
Groq `openai/gpt-oss-120b`, the default model. By the time the forms set ran, that model's daily
quota was spent, so it ran on the first fallback, `openai/gpt-oss-20b`.

| Metric | Test set (fictional) | Real set (GDPR) | Forms set | Definition |
| --- | --- | --- | --- | --- |
| Questions passed | 20 / 20 | 18 / 18 | 17 / 18 | Every applicable check below passed |
| Retrieval hit@5 | 100% | 100% | 92% | The expected documents were retrieved and the supporting passage is inside a retrieved chunk |
| Abstention accuracy | 100% | 100% | 100% | Answered when it should, refused when it should |
| Citation correctness | 100% | 100% | 100% | At least one citation, and every citation is an expected document |
| Answer keyword accuracy | 100% | 100% | 92% | The answer contains the expected facts |
| Distractor resilience | 100% | n/a | n/a | Cited the right document and not the near-miss |
| Average latency | 3.8 s | 5.4 s | 4.1 s | Most questions took 0.7 to 2 seconds; a few waited on the rate limit |

Per-question tables: [`eval/results.md`](../eval/results.md),
[`eval/results_real.md`](../eval/results_real.md) and
[`eval/results_forms.md`](../eval/results_forms.md).

**t13 now passes in a full run.** The run before this one scored 19 / 20: "What is the password
for the guest Wi-Fi network?" got an explanation of why the password is not written down, where a
refusal was expected. That came from the change that allows longer answers. One sentence was added
to the prompt (when the requested fact is not stated, refuse, even if the sources explain why it
is missing), and this run is the first complete one since. The earlier run was on
`qwen/qwen3.8-27b` and this one on `gpt-oss-120b`, so the two differ by model as well as by prompt.

**One question is borderline.** r12 asks two things at once: how quickly a breach must be reported
and what the highest fine is. Those facts are on pages 52 and 83. In one earlier run it
failed: the two passages were not both retrieved, the model said the evidence was insufficient, and
the system refused. In the last two runs the second pass found both and it passed; in this one that
took 17 seconds. I count
that as a question the system can get right, not one it reliably does. Across every run, a failure
was always a wrong refusal or a provider error: no question in either set produced an unsupported
answer.

## The forms set: a filled-in form and a handwritten scan

Added on 13 Oct 2026, after two outside reviews of the system on a medical intake form and after
OCR was added. 18 questions: 13 on the form (8 single-fact, 2 multi-part, 3 unanswerable) and 5 on
the handwritten page (3 answerable, 2 unanswerable).

**Result: 17 / 18** on `gpt-oss-20b`. All 13 form questions passed, including the three that must
be refused and the phone-number question (f08). On the handwritten page, 4 of 5 passed.

| Check | Form (13 questions) | Handwritten page (5 questions) |
| --- | --- | --- |
| Passed | 13 / 13 | 4 / 5 |
| Answerable questions answered with the right fact and source | 10 / 10 | 2 / 3 |
| Unanswerable questions refused | 3 / 3 | 2 / 2 |
| The exact supporting text was in the passages sent to the model | 10 / 10 | 2 / 3 |
| Unanswerable questions stopped by the gate, before the model | 0 / 3 | 0 / 2 |

Two things to read from this:

- **The one failure is the OCR, not the search or the model.** s03 asks for the date on the
  handwritten page. The page says 16-11-2024; the OCR read 16-11-2624. The system found the page,
  answered and cited it, and the answer did not contain the right date. The question was written
  knowing this and is kept because it is what a user would ask.
- **All five refusals came from the model, none from the gate.** The best passages for the
  unanswerable questions score 0.59 to 0.72 against a gate of 0.40: "What is the patient's blood
  type?" is close in meaning to a patient form. The model was sent the passages and said the fact
  was not there. On a form, the gate does no work; the prompt and the citation check do.

This is one run on one model. The other two answerable questions on the handwritten page passed
because the OCR happened to read "22CDA602" and "Data Science" correctly.

Earlier spot checks on the form are described in step 8 of the history below. In one of them the
weakest model gave the wrong phone number for the patient; that question (f08) is in the set.

## The report set: one long document, five levels

Added on 13 Oct 2026. The document is a 48-page undergraduate project report (96 chunks): chapters,
a table of contents, a bibliography, source code, and example text in Hindi, French and Tamil. 21
questions: 5 at level 1, 5 at level 2, 3 at level 3, 4 at level 4 and 4 at level 5.

**Status: one partial run, not saved.** On `qwen/qwen3.8-27b`, the last model in the chain, with
the other two out of quota:

| Level | Questions | Ran | Passed |
| --- | --- | --- | --- |
| 1. One fact | 5 | 5 | 5 |
| 2. Several facts, one passage | 5 | 5 | 5 |
| 3. Facts from different places | 3 | 3 | 3 |
| 4. A near-miss sits close by | 4 | 4 | 4 |
| 5. Must be refused | 4 | 1 | 1 |

The last three questions, all level 5, returned `LLM_RATE_LIMITED`. Whether the system refuses
them is not known. Because the run has provider errors it was not written to
`eval/results_report.md`, and the question bank shows this set as not run. Run
`python eval/run_eval.py --dataset report` to complete it.

**The questions were reworded once, before any run with the AI model.** In the first draft every
question named "the offensive language detection project". A retrieval check without the AI model
showed 4 of 17 answerable questions had lost their passage: dense search had it in the top 10, and
the reranker ranked the title page, certificate and declaration above it because they repeat that
phrase. Those four were reworded the way a reader would ask (for example "Which GPU was used to
fine-tune the Distil-BERT model?"), after which all 17 passages were found. That is a change made
after seeing a result, so the set is not a blind test, and the weakness it exposed is real: it is
listed under [limitations](SYSTEM_DESIGN.md#limitations).

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

10. **Longer answers, and a path for summaries.** The prompt asked for short answers, so an
    explanation came back as one clipped line and "Summarise this document" was refused. Answer
    length now follows the question, and a whole-document question reads passages spread across the
    library. This cost one test question (t13, described under Results) until the prompt was
    tightened.

11. **OCR and a third prepared set.** Scanned pages are now read with a local OCR model, and a
    form and a handwritten page were added to the corpus with 18 questions. The first complete run
    of all three sets on the 11 documents: 20 / 20, 18 / 18 and 17 / 18.

12. **A long report, levels, and an optional second reader.** A 48-page project report joined the
    corpus with 21 questions in five levels, every reported question got a level, and a vision
    model can now be switched on to re-read pages the local OCR is unsure of. The report set has
    one partial run: 18 of 18 passed before the quota ran out.

Steps 2 to 10 used information from outside the dev set, including the earlier real-set runs, so the
real-set score is not a clean held-out number. No change was made to target r12 specifically.

## Retrieval and fusion evaluation (no LLM)

Retrieval measured on its own, so a good or bad LLM cannot hide it. A chunk is relevant if it
contains the gold evidence text for the question. 684 chunks, 13 questions per set. Full output,
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
| BM25 only | 0.54 | 0.54 | 0.54 | 0.50 | 0.48 | 3 ms | 5 ms |
| Dense only | 0.81 | 0.96 | 1.00 | 0.80 | 0.82 | 56 ms | 73 ms |
| Hybrid (BM25 + dense) | 0.81 | 0.81 | 0.96 | 0.79 | 0.76 | 62 ms | 82 ms |
| **Dense + reranker (default)** | 0.88 | 0.96 | 1.00 | 0.78 | 0.80 | 1259 ms | 1934 ms |
| Hybrid + reranker | 0.88 | 0.96 | 0.96 | 0.78 | 0.80 | 1932 ms | 2756 ms |

On the fictional documents every method reaches Recall@5 of 1.00 and an MRR of 0.94 to 1.00, so
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
  unchanged, and MRR dips from 0.80 to 0.78. It costs 0.7 to 1.3 s per question on CPU, depending on the run.
- **Why it is still on.** On a private markdown document with tables (10 questions, measured by
  hand) dense search put the evidence in the top 5 for 6 questions and the reranker for all 10, and
  on the dev set it took 12 of 13 to 13 of 13. That is weaker evidence than the table above,
  because I cannot publish that document. On the published sets alone, dense-only would be a
  defensible default and about a second faster; `ENABLE_RERANKER=false` gives that.

## Read these numbers with care

- **Small sets, written by me.** 98 questions in total. This shows the pipeline works as designed
  on two kinds of document; it is not a benchmark.
- **The model already knows the GDPR.** A correct answer on the real set does not prove grounding
  by itself. The fictional set is what proves that. The real set shows retrieval, citation and
  refusal on long real text.
- **Latency depends on the free tier.** Groq allows 8,000 tokens per minute on this plan. In these
  runs most questions took 0.7 to 2 seconds; the ones that took 10 to 40 seconds were waiting for
  the limit to reset or went through a second retrieval pass.
- **The three sets did not all run on the same model.** The test and real sets ran on the default,
  `gpt-oss-120b`. The forms set ran on `gpt-oss-20b` because the default's daily quota ran out. The
  runs before these, on `qwen/qwen3.8-27b`, scored 19 / 20 and 18 / 18.
- **One run each.** Answers from an LLM vary between runs, and r12 has gone both ways.
- **Answer accuracy is a keyword match**, which checks that the right number or name is present,
  not that the whole sentence is correct.

## Reproduce

```bash
python eval/run_eval.py                   # test set, writes eval/results.md
python eval/run_eval.py --dataset real    # real set, writes eval/results_real.md
python eval/run_eval.py --dataset forms   # forms set, writes eval/results_forms.md
python eval/run_eval.py --dataset report  # report set, writes eval/results_report.md
python eval/question_bank.py              # regroup the saved results by level and format (no LLM calls)
python eval/run_eval.py --tune            # gate threshold sweep on the dev set (no LLM calls)
python eval/run_eval.py --retrieval       # retrieval and fusion evaluation (no LLM calls)
```

A full run of one set costs roughly 30,000 to 50,000 tokens, so a 200,000-token daily quota covers only a
handful. The CLI and `POST /eval` call the same `run_evaluation` function. The CLI uses a clean
in-memory store, so it never touches the server's data. If a run is cut short by a provider error,
the CLI prints the result but does not overwrite the saved one.

## Automated tests

```bash
pytest          # 194 tests, about half a minute, no API key or network needed
ruff check .
```

Latest run: **194 passed, 0 failed**. The full output is recorded in
[`tests/RESULTS.md`](../tests/RESULTS.md). The same two commands run on every push
(`.github/workflows/ci.yml`).

| Area | What is tested |
| --- | --- |
| Chunking | Size limit, overlap, no lost text, metadata |
| Dedupe | Same file twice keeps one set of chunks; same name with new content replaces |
| Similarity | Distance converts correctly; a close match outscores a far one |
| Retrieval | A known question returns the expected chunk; PDF page numbers; BM25 fusion; reranking; chunks next to a hit are added, gaps between hits first |
| API | Ingest then ask end to end; list, delete, reset |
| Scanned PDFs | A picture of text is uploaded, read with the real OCR model and found by asking; typed PDFs never reach OCR; a scan over the page limit is refused whole; clear errors when nothing is recognised or the OCR packages are missing |
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
