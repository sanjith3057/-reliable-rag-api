# Evaluation results (test set)

Run: 2026-10-12T23:03:50  
Config: llm=groq/qwen/qwen3.8-27b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.4, hybrid=False, reranker=True, judge=False

| Metric | Value |
| --- | --- |
| Questions passed | 20 / 20 |
| Retrieval hit@k | 100% |
| Abstention accuracy | 100% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Distractor resilience | 100% |
| Average latency | 13199 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| t01 | answerable | yes | true / true | expense_policy.pdf | 7115 ms |
| t02 | answerable | yes | true / true | security_handbook.md | 1592 ms |
| t03 | answerable | yes | true / true | pricing_sheet.txt | 4398 ms |
| t04 | answerable | yes | true / true | orbit_b2_spec.md | 1333 ms |
| t05 | answerable | yes | true / true | it_notice.txt | 33261 ms |
| t06 | answerable | yes | true / true | expense_policy.pdf | 26755 ms |
| t07 | multi | yes | true / true | hr_policy_2024.md, hr_policy_2025.md | 2749 ms |
| t08 | multi | yes | true / true | orbit_a1_spec.md, orbit_b2_spec.md | 2451 ms |
| t09 | multi | yes | true / true | pricing_sheet.txt | 21161 ms |
| t10 | multi | yes | true / true | security_handbook.md, expense_policy.pdf | 10960 ms |
| t11 | unanswerable | yes | false / false | - | 31529 ms |
| t12 | unanswerable | yes | false / false | - | 25522 ms |
| t13 | unanswerable | yes | false / false | - | 10216 ms |
| t14 | unanswerable | yes | false / false | - | 22449 ms |
| t15 | unanswerable | yes | false / false | - | 23366 ms |
| t16 | distractor | yes | true / true | hr_policy_2025.md | 1859 ms |
| t17 | distractor | yes | true / true | hr_policy_2024.md | 12378 ms |
| t18 | distractor | yes | true / true | orbit_a1_spec.md | 4536 ms |
| t19 | distractor | yes | false / false | - | 1590 ms |
| t20 | distractor | yes | false / false | - | 18755 ms |
