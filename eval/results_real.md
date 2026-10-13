# Evaluation results (real set)

Run: 2026-10-13T08:13:36  
Config: llm=groq/openai/gpt-oss-120b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.4, hybrid=False, reranker=True, judge=False

| Metric | Value |
| --- | --- |
| Questions passed | 18 / 18 |
| Retrieval hit@k | 100% |
| Abstention accuracy | 100% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Distractor resilience | n/a |
| Average latency | 5350 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| r01 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 11193 ms |
| r02 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 1442 ms |
| r03 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 958 ms |
| r04 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 795 ms |
| r05 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 1321 ms |
| r06 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 1656 ms |
| r07 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 708 ms |
| r08 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 824 ms |
| r09 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 2018 ms |
| r10 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 1180 ms |
| r11 | multi | yes | true / true | gdpr_regulation_2016_679.pdf | 937 ms |
| r12 | multi | yes | true / true | gdpr_regulation_2016_679.pdf | 16548 ms |
| r13 | multi | yes | true / true | gdpr_regulation_2016_679.pdf | 1338 ms |
| r14 | unanswerable | yes | false / false | - | 10641 ms |
| r15 | unanswerable | yes | false / false | - | 1235 ms |
| r16 | unanswerable | yes | false / false | - | 39521 ms |
| r17 | unanswerable | yes | false / false | - | 1875 ms |
| r18 | unanswerable | yes | false / false | - | 2119 ms |
