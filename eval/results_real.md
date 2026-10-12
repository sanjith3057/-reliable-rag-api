# Evaluation results (real set)

Run: 2026-10-12T17:59:29  
Config: llm=groq/openai/gpt-oss-20b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.5, hybrid=False, reranker=True

| Metric | Value |
| --- | --- |
| Questions passed | 18 / 18 |
| Retrieval hit@k | 100% |
| Abstention accuracy | 100% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Distractor resilience | n/a |
| Average latency | 8672 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| r01 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 6187 ms |
| r02 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 1218 ms |
| r03 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 1050 ms |
| r04 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 1337 ms |
| r05 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 1578 ms |
| r06 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 4291 ms |
| r07 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 11078 ms |
| r08 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 9220 ms |
| r09 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 11298 ms |
| r10 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 10294 ms |
| r11 | multi | yes | true / true | gdpr_regulation_2016_679.pdf | 13418 ms |
| r12 | multi | yes | true / true | gdpr_regulation_2016_679.pdf | 24531 ms |
| r13 | multi | yes | true / true | gdpr_regulation_2016_679.pdf | 12342 ms |
| r14 | unanswerable | yes | false / false | - | 11569 ms |
| r15 | unanswerable | yes | false / false | - | 12982 ms |
| r16 | unanswerable | yes | false / false | - | 10987 ms |
| r17 | unanswerable | yes | false / false | - | 12269 ms |
| r18 | unanswerable | yes | false / false | - | 440 ms |
