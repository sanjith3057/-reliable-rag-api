# Evaluation results (real set)

Run: 2026-10-12T23:42:13  
Config: llm=groq/qwen/qwen3.8-27b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.4, hybrid=False, reranker=True, judge=False

| Metric | Value |
| --- | --- |
| Questions passed | 18 / 18 |
| Retrieval hit@k | 100% |
| Abstention accuracy | 100% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Distractor resilience | n/a |
| Average latency | 20286 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| r01 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 9930 ms |
| r02 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 2776 ms |
| r03 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 28331 ms |
| r04 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 2791 ms |
| r05 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 2979 ms |
| r06 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 23849 ms |
| r07 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 33356 ms |
| r08 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 12050 ms |
| r09 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 28912 ms |
| r10 | answerable | yes | true / true | gdpr_regulation_2016_679.pdf | 29673 ms |
| r11 | multi | yes | true / true | gdpr_regulation_2016_679.pdf | 24308 ms |
| r12 | multi | yes | true / true | gdpr_regulation_2016_679.pdf | 11212 ms |
| r13 | multi | yes | true / true | gdpr_regulation_2016_679.pdf | 19904 ms |
| r14 | unanswerable | yes | false / false | - | 28021 ms |
| r15 | unanswerable | yes | false / false | - | 26029 ms |
| r16 | unanswerable | yes | false / false | - | 29065 ms |
| r17 | unanswerable | yes | false / false | - | 26937 ms |
| r18 | unanswerable | yes | false / false | - | 25020 ms |
