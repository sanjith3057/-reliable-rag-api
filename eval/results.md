# Evaluation results (test set)

Run: 2026-10-12T18:02:45  
Config: llm=groq/openai/gpt-oss-20b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.5, hybrid=False, reranker=True

| Metric | Value |
| --- | --- |
| Questions passed | 20 / 20 |
| Retrieval hit@k | 100% |
| Abstention accuracy | 100% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Distractor resilience | 100% |
| Average latency | 5573 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| t01 | answerable | yes | true / true | expense_policy.pdf | 6494 ms |
| t02 | answerable | yes | true / true | security_handbook.md | 1309 ms |
| t03 | answerable | yes | true / true | pricing_sheet.txt | 1301 ms |
| t04 | answerable | yes | true / true | orbit_b2_spec.md | 1250 ms |
| t05 | answerable | yes | true / true | it_notice.txt | 1185 ms |
| t06 | answerable | yes | true / true | expense_policy.pdf | 744 ms |
| t07 | multi | yes | true / true | hr_policy_2024.md, hr_policy_2025.md | 8522 ms |
| t08 | multi | yes | true / true | orbit_a1_spec.md, orbit_b2_spec.md | 2972 ms |
| t09 | multi | yes | true / true | pricing_sheet.txt | 1457 ms |
| t10 | multi | yes | true / true | security_handbook.md, expense_policy.pdf | 1266 ms |
| t11 | unanswerable | yes | false / false | - | 5166 ms |
| t12 | unanswerable | yes | false / false | - | 1525 ms |
| t13 | unanswerable | yes | false / false | - | 10255 ms |
| t14 | unanswerable | yes | false / false | - | 12734 ms |
| t15 | unanswerable | yes | false / false | - | 453 ms |
| t16 | distractor | yes | true / true | hr_policy_2025.md | 10352 ms |
| t17 | distractor | yes | true / true | hr_policy_2024.md | 11475 ms |
| t18 | distractor | yes | true / true | orbit_a1_spec.md | 10356 ms |
| t19 | distractor | yes | false / false | - | 11685 ms |
| t20 | distractor | yes | false / false | - | 10957 ms |
