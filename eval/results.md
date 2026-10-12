# Evaluation results (test set)

Run: 2026-10-12T23:32:21  
Config: llm=groq/qwen/qwen3.8-27b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.4, hybrid=False, reranker=True, judge=False

| Metric | Value |
| --- | --- |
| Questions passed | 19 / 20 |
| Retrieval hit@k | 100% |
| Abstention accuracy | 95% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Distractor resilience | 100% |
| Average latency | 15597 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| t01 | answerable | yes | true / true | expense_policy.pdf | 9835 ms |
| t02 | answerable | yes | true / true | security_handbook.md | 2313 ms |
| t03 | answerable | yes | true / true | pricing_sheet.txt | 2403 ms |
| t04 | answerable | yes | true / true | orbit_b2_spec.md | 12347 ms |
| t05 | answerable | yes | true / true | it_notice.txt | 7887 ms |
| t06 | answerable | yes | true / true | expense_policy.pdf | 25445 ms |
| t07 | multi | yes | true / true | hr_policy_2024.md, hr_policy_2025.md | 25014 ms |
| t08 | multi | yes | true / true | orbit_a1_spec.md, orbit_b2_spec.md | 25640 ms |
| t09 | multi | yes | true / true | pricing_sheet.txt | 28248 ms |
| t10 | multi | yes | true / true | security_handbook.md, expense_policy.pdf | 7936 ms |
| t11 | unanswerable | yes | false / false | - | 31870 ms |
| t12 | unanswerable | yes | false / false | - | 28623 ms |
| t13 | unanswerable | NO | false / true | security_handbook.md | 1799 ms |
| t14 | unanswerable | yes | false / false | - | 32423 ms |
| t15 | unanswerable | yes | false / false | - | 25375 ms |
| t16 | distractor | yes | true / true | hr_policy_2025.md | 2732 ms |
| t17 | distractor | yes | true / true | hr_policy_2024.md | 22740 ms |
| t18 | distractor | yes | true / true | orbit_a1_spec.md | 2255 ms |
| t19 | distractor | yes | false / false | - | 2555 ms |
| t20 | distractor | yes | false / false | - | 14496 ms |
