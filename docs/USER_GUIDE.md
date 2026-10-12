# User guide

How to use Reliable RAG from the browser. No programming needed once it is running.
To install and start it, see [Run it](../README.md#run-it) in the README.

- [1. Open the console](#1-open-the-console)
- [2. Add documents](#2-add-documents)
- [3. Ask a question](#3-ask-a-question)
- [4. Read the answer](#4-read-the-answer)
- [5. When it says "not available"](#5-when-it-says-not-available)
- [6. Measure how well it works](#6-measure-how-well-it-works)
- [7. Fix a problem](#7-fix-a-problem)
- [8. Common questions](#8-common-questions)

## 1. Open the console

Go to **http://localhost:8000**. The top right shows **Ready** when the server is up.

![The web console](images/console.png)

The left side is your **library**: the documents the assistant can read. The right side has two
tabs, **Ask** and **Evaluate**.

If the server was started with a password (`API_KEY`), the page asks for it the first time. It is
kept only until you close the browser tab.

## 2. Add documents

**Your own files.** Click **Add documents**, or drag files onto that box. You can add several at once.

| Allowed | Limit |
| --- | --- |
| PDF, TXT, Markdown (`.md`) | 10 MB per file |
| PDFs with real text | 500 pages per PDF |

**The samples.** Click **Load sample docs** to add 9 demo documents: 8 short documents from a
made-up company called Lumenfold, and the 88-page GDPR regulation. This takes about a minute.

Each document appears in the library with the number of pieces ("chunks") it was split into.

- Click the **×** next to a document to remove it.
- **Clear all** empties the library.
- Uploading the same file again replaces it. Uploading a changed file with the same name replaces
  the old version.

## 3. Ask a question

Type a question in the box and click **Ask**. With the sample documents loaded, a few starter
questions appear under the box; click one to try it.

Good questions are specific:

| Works well | Works less well |
| --- | --- |
| "How many days of annual leave do employees get in 2025?" | "Tell me about leave" |
| "How quickly must a personal data breach be reported?" | "Summarise this document" |
| "Which scanner has the longer battery life, the Orbit A1 or the Orbit B2?" | "What do you think of this policy?" |

Questions can be up to 1,000 characters. You can ask two things at once ("How fast must a breach be
reported, and what is the highest fine?"); the assistant looks up each part.

## 4. Read the answer

An answer has three parts.

| Part | What it tells you |
| --- | --- |
| **The answer** | Short and direct, written only from your documents |
| **Grounded · N sources** | How many passages back the answer |
| **Evidence** | For each source: the document name, the page (for PDFs), the exact sentences used, and a score |

The **evidence** quotes the lines of the passage that contain the words of the answer, so you can
check it at a glance. On a form, a short value is shown with its field label, for example
"PREFERRED NAME Maggie".

The **similarity** score (0 to 1) says how close the passage is in meaning to your question. Around 0.8 is a
very close match. Around 0.55 is related but loosely worded. It is a search score, not a measure of
how correct the answer is.

**Always read the evidence.** The answer is only as trustworthy as the sentence quoted under it.

Sometimes an answer carries a **warning**. There are two kinds:

- **A number that is not in the cited passage.** That can be an honest calculation (the document
  says "from 65% to 100%" and the answer says "35 points"), or it can be a mistake.
- **Wording that is not in the cited passage at all.** The answer was worked out or inferred, not
  read off the page.

Either way, check the evidence before relying on the answer. Be careful with questions that ask
for a judgement ("Is this safe?", "Is this allowed?"). The assistant may add a conclusion that
your document does not state.

## 5. When it says "not available"

The assistant answers "The information is not available in the provided documents" in three cases.

| Why | What happened | What to try |
| --- | --- | --- |
| Nothing related was found | The question is not about anything in the library. The AI model was not even asked. | Check that the right document is uploaded |
| Related text, but no answer in it | Passages on the topic were found, but none states the answer | Rephrase with words the document uses, or ask something narrower |
| The answer could not be tied to a passage | The AI model produced an answer but could not point to a source, so it was discarded | Rephrase, or ask about one fact at a time |

A refusal is the system working as intended. Try "What is the capital of Australia?" with only the
sample documents loaded: the correct result is "not available", because the documents do not say.

## 6. Measure how well it works

Open the **Evaluate** tab, choose a question set, and click **Run evaluation**.

| Question set | Use it to |
| --- | --- |
| **My documents** | Test the assistant on whatever is in your library. It writes the questions itself. |
| **Test set** | Run the 20 prepared questions about the sample company documents |
| **Real set** | Run the 18 prepared questions about the GDPR regulation |
| **Dev set** | The questions used while tuning. Not a fair test. |

The Test, Real and Dev sets need the sample documents, so click **Load sample docs** first.

Tick **Also grade each answer with an LLM judge** to have a second AI pass check each answer.
It costs extra quota.

### How "My documents" works

1. The assistant picks passages from your library and writes one question about each.
2. A question is kept only if its expected answer really is in that passage.
3. Three general-knowledge questions are added (such as "Which country won the 2018 FIFA World
   Cup?"). Your documents do not answer these, so the right response is a refusal.
4. Every question is then asked in the normal way and scored.

### Reading the results

| Tile | Question it answers |
| --- | --- |
| **Questions passed** | How many questions passed every check |
| **Retrieval hit@k** | Did search find the right passage? |
| **Abstention accuracy** | Did it answer when it should, and refuse when it should? |
| **Citation correctness** | Did it cite the right document, and nothing when refusing? |
| **Answer accuracy** | Does the answer contain the expected fact? |
| **Distractor resilience** | Did it avoid a similar-looking but wrong document? (Test set only) |
| **Faithfulness (judged)** | Did the judge find every claim supported by the cited text? |
| **Relevance (judged)** | Did the judge find that the answer addresses the question? |
| **Average latency** | How long an answer took |

The table under the tiles lists each question, what was expected, what happened and which
document was cited.

**A "fail" is not always a wrong answer.** Answer accuracy looks for an expected word or number.
A correct answer in different words can miss it. When Faithfulness and Relevance are 100% and
Answer accuracy is lower, this is usually why. Check the row before trusting the number.

## 7. Fix a problem

| What you see | What it means | What to do |
| --- | --- | --- |
| "Only PDF, TXT, MD are accepted" | The file type is not supported | Convert the file to PDF or text |
| "No text could be extracted" | The PDF is scanned images, not text | Use a PDF with selectable text; scanned pages are not supported |
| "File exceeds the 10 MB limit" | The file is too big | Split it or compress it |
| "PDFs are limited to 500 pages" | The PDF is too long | Split it into parts |
| "No documents have been ingested yet" | The library is empty | Add a document first |
| "Too many requests. Try again in N seconds." | You hit the per-minute limit | Wait the stated time |
| "The language model's usage limit has been reached" | The free AI quota is spent for now | Wait the stated time, or use another key or provider in `.env` |
| "The language model could not be reached" | The AI provider did not answer | Check your internet connection and the key in `.env`, then retry |
| "A valid X-API-Key header is required" | The server needs its password | Enter the key when the page asks |
| "This key is read-only" | Your key can ask but not change things | Use the admin key to upload, delete or evaluate |
| "This question set needs documents that are not in the library" | A prepared set was run without the sample documents | Click **Load sample docs**, then run it again |
| The page looks out of date | The browser kept an old copy | Press Ctrl+F5 |
| The status never shows **Ready** | The server is not running | Start it again; see [Run it](../README.md#run-it) |

Every error message carries a short request ID. If you report a problem, include it: it finds the
matching line in the server log.

## 8. Common questions

**Does it use the internet?**
Only for the final step, where the passages and your question are sent to the AI provider (Groq by
default) to write the answer. Reading, splitting, storing and searching your documents all happen
on your machine.

**Are my documents kept?**
The text of each piece is stored in the `chroma_data` folder so it can be searched. The original
file is not kept. **Clear all** removes everything.

**Can it answer from general knowledge?**
No, on purpose. If your documents do not say it, it will not say it.

**Why did it refuse something I can see in the document?**
Search may not have found that passage, most often when the question uses different words from
the document, or when the answer sits in a table that was split in two. Rephrase with the
document's own wording.

**Can several people use it at once?**
Yes, but everyone shares one library and the per-minute limits are counted per client address.

**Can I use a different AI model?**
Yes. Set `LLM_PROVIDER` to `groq`, `openai` or `gemini` in `.env`, add that provider's key, and
restart. See [settings](SYSTEM_DESIGN.md#settings).
