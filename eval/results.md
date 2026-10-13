# Evaluation results (test set)

Run: 2026-10-13T08:11:00  
Config: llm=groq/openai/gpt-oss-120b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.4, hybrid=False, reranker=True, judge=False

| Metric | Value |
| --- | --- |
| Questions passed | 20 / 20 |
| Retrieval hit@k | 100% |
| Abstention accuracy | 100% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Distractor resilience | 100% |
| Average latency | 3762 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| t01 | answerable | yes | true / true | expense_policy.pdf | 11750 ms |
| t02 | answerable | yes | true / true | security_handbook.md | 1030 ms |
| t03 | answerable | yes | true / true | pricing_sheet.txt | 910 ms |
| t04 | answerable | yes | true / true | orbit_b2_spec.md | 820 ms |
| t05 | answerable | yes | true / true | it_notice.txt | 844 ms |
| t06 | answerable | yes | true / true | expense_policy.pdf | 1274 ms |
| t07 | multi | yes | true / true | hr_policy_2024.md, hr_policy_2025.md | 850 ms |
| t08 | multi | yes | true / true | orbit_a1_spec.md, orbit_b2_spec.md | 923 ms |
| t09 | multi | yes | true / true | pricing_sheet.txt | 793 ms |
| t10 | multi | yes | true / true | security_handbook.md, expense_policy.pdf | 741 ms |
| t11 | unanswerable | yes | false / false | - | 1740 ms |
| t12 | unanswerable | yes | false / false | - | 7018 ms |
| t13 | unanswerable | yes | false / false | - | 1642 ms |
| t14 | unanswerable | yes | false / false | - | 26181 ms |
| t15 | unanswerable | yes | false / false | - | 3115 ms |
| t16 | distractor | yes | true / true | hr_policy_2025.md | 855 ms |
| t17 | distractor | yes | true / true | hr_policy_2024.md | 1128 ms |
| t18 | distractor | yes | true / true | orbit_a1_spec.md | 755 ms |
| t19 | distractor | yes | false / false | - | 1306 ms |
| t20 | distractor | yes | false / false | - | 11557 ms |
