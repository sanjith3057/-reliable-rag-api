# Evaluation results (test set)

Run: 2026-10-12T19:02:41  
Config: llm=groq/openai/gpt-oss-120b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.5, hybrid=False, reranker=True

| Metric | Value |
| --- | --- |
| Questions passed | 10 / 20 |
| Retrieval hit@k | 100% |
| Abstention accuracy | 50% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Distractor resilience | 100% |
| Average latency | 46079 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| t01 | answerable | yes | true / true | expense_policy.pdf | 1757 ms |
| t02 | answerable | NO | true / error: LLM_UNAVAILABLE | - | 60802 ms |
| t03 | answerable | yes | true / true | pricing_sheet.txt | 1731 ms |
| t04 | answerable | NO | true / error: LLM_UNAVAILABLE | - | 60894 ms |
| t05 | answerable | yes | true / true | it_notice.txt | 42151 ms |
| t06 | answerable | NO | true / error: LLM_UNAVAILABLE | - | 60868 ms |
| t07 | multi | yes | true / true | hr_policy_2024.md, hr_policy_2025.md | 49897 ms |
| t08 | multi | NO | true / error: LLM_UNAVAILABLE | - | 61988 ms |
| t09 | multi | NO | true / error: LLM_UNAVAILABLE | - | 61872 ms |
| t10 | multi | yes | true / true | security_handbook.md, expense_policy.pdf | 1849 ms |
| t11 | unanswerable | NO | false / error: LLM_UNAVAILABLE | - | 60998 ms |
| t12 | unanswerable | yes | false / false | - | 70391 ms |
| t13 | unanswerable | NO | false / error: LLM_UNAVAILABLE | - | 62111 ms |
| t14 | unanswerable | yes | false / false | - | 72712 ms |
| t15 | unanswerable | yes | false / false | - | 475 ms |
| t16 | distractor | NO | true / error: LLM_UNAVAILABLE | - | 60885 ms |
| t17 | distractor | yes | true / true | hr_policy_2024.md | 13075 ms |
| t18 | distractor | NO | true / error: LLM_UNAVAILABLE | - | 60943 ms |
| t19 | distractor | NO | false / error: LLM_UNAVAILABLE | - | 53879 ms |
| t20 | distractor | yes | false / false | - | 62307 ms |
