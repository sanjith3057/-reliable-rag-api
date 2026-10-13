# Evaluation results (forms set)

Run: 2026-10-13T08:15:45  
Config: llm=groq/openai/gpt-oss-20b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.4, hybrid=False, reranker=True, judge=False

| Metric | Value |
| --- | --- |
| Questions passed | 17 / 18 |
| Retrieval hit@k | 92% |
| Abstention accuracy | 100% |
| Citation correctness | 100% |
| Answer keyword accuracy | 92% |
| Distractor resilience | n/a |
| Average latency | 4136 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| f01 | answerable | yes | true / true | medical_intake_form.pdf | 12081 ms |
| f02 | answerable | yes | true / true | medical_intake_form.pdf | 1026 ms |
| f03 | answerable | yes | true / true | medical_intake_form.pdf | 833 ms |
| f04 | answerable | yes | true / true | medical_intake_form.pdf | 677 ms |
| f05 | answerable | yes | true / true | medical_intake_form.pdf | 1286 ms |
| f06 | answerable | yes | true / true | medical_intake_form.pdf | 705 ms |
| f07 | answerable | yes | true / true | medical_intake_form.pdf | 1514 ms |
| f08 | answerable | yes | true / true | medical_intake_form.pdf | 1888 ms |
| f09 | multi | yes | true / true | medical_intake_form.pdf | 1384 ms |
| f10 | multi | yes | true / true | medical_intake_form.pdf | 22511 ms |
| f11 | unanswerable | yes | false / false | - | 2140 ms |
| f12 | unanswerable | yes | false / false | - | 1563 ms |
| f13 | unanswerable | yes | false / false | - | 1330 ms |
| s01 | answerable | yes | true / true | handwritten_assignment_scan.pdf | 1304 ms |
| s02 | answerable | yes | true / true | handwritten_assignment_scan.pdf | 17173 ms |
| s03 | answerable | NO | true / true | handwritten_assignment_scan.pdf | 1463 ms |
| s04 | unanswerable | yes | false / false | - | 1990 ms |
| s05 | unanswerable | yes | false / false | - | 3580 ms |
