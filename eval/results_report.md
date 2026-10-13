# Evaluation results (report set)

Run: 2026-10-13T10:36:22  
Config: llm=groq/qwen/qwen3.8-27b, embedder=BAAI/bge-small-en-v1.5, top_k=5, similarity_threshold=0.4, hybrid=False, reranker=True, judge=False

| Metric | Value |
| --- | --- |
| Questions passed | 21 / 21 |
| Retrieval hit@k | 100% |
| Abstention accuracy | 100% |
| Citation correctness | 100% |
| Answer keyword accuracy | 100% |
| Distractor resilience | n/a |
| Average latency | 6948 ms |

| ID | Type | Passed | Answerable (expected / got) | Cited | Latency |
| --- | --- | --- | --- | --- | --- |
| p01 | answerable | yes | true / true | project_report_offensive_language.pdf | 7034 ms |
| p02 | answerable | yes | true / true | project_report_offensive_language.pdf | 1708 ms |
| p03 | answerable | yes | true / true | project_report_offensive_language.pdf | 1388 ms |
| p04 | answerable | yes | true / true | project_report_offensive_language.pdf | 1380 ms |
| p05 | answerable | yes | true / true | project_report_offensive_language.pdf | 1576 ms |
| p06 | answerable | yes | true / true | project_report_offensive_language.pdf | 1768 ms |
| p07 | answerable | yes | true / true | project_report_offensive_language.pdf | 1843 ms |
| p08 | answerable | yes | true / true | project_report_offensive_language.pdf | 1471 ms |
| p09 | answerable | yes | true / true | project_report_offensive_language.pdf | 1382 ms |
| p10 | answerable | yes | true / true | project_report_offensive_language.pdf | 1330 ms |
| p11 | multi | yes | true / true | project_report_offensive_language.pdf | 2360 ms |
| p12 | multi | yes | true / true | project_report_offensive_language.pdf | 1590 ms |
| p13 | multi | yes | true / true | project_report_offensive_language.pdf | 12001 ms |
| p14 | multi | yes | true / true | project_report_offensive_language.pdf | 1607 ms |
| p15 | multi | yes | true / true | project_report_offensive_language.pdf | 9050 ms |
| p16 | answerable | yes | true / true | project_report_offensive_language.pdf | 1573 ms |
| p17 | answerable | yes | true / true | project_report_offensive_language.pdf | 1388 ms |
| p18 | unanswerable | yes | false / false | - | 23146 ms |
| p19 | unanswerable | yes | false / false | - | 23187 ms |
| p20 | unanswerable | yes | false / false | - | 26019 ms |
| p21 | unanswerable | yes | false / false | - | 23106 ms |
