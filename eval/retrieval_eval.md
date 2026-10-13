# Retrieval and fusion evaluation

Corpus: 684 chunks from 12 documents. No LLM is called.
A chunk counts as relevant if it contains the gold evidence text for the question.

- **Recall@K**: share of the gold evidence found in the top K chunks (a two-fact question needs both).
- **MRR**: 1 / rank of the first relevant chunk, averaged.
- **nDCG@K**: like recall, but rewards relevant chunks for being nearer the top.

## Fictional documents (13 questions)

| Retrieval | Recall@3 | Recall@5 | Recall@10 | MRR | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- |
| BM25 only | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Dense only | 0.92 | 1.00 | 1.00 | 0.94 | 0.95 | 0.95 |
| Hybrid (BM25 + dense) | 1.00 | 1.00 | 1.00 | 0.96 | 0.97 | 0.97 |
| Dense + reranker (default) | 0.92 | 1.00 | 1.00 | 0.94 | 0.96 | 0.96 |
| Hybrid + reranker | 0.92 | 1.00 | 1.00 | 0.94 | 0.96 | 0.96 |

## Real document (GDPR) (13 questions)

| Retrieval | Recall@3 | Recall@5 | Recall@10 | MRR | nDCG@5 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- |
| BM25 only | 0.54 | 0.54 | 0.54 | 0.50 | 0.48 | 0.48 |
| Dense only | 0.81 | 0.96 | 1.00 | 0.80 | 0.82 | 0.83 |
| Hybrid (BM25 + dense) | 0.81 | 0.81 | 0.96 | 0.79 | 0.76 | 0.81 |
| Dense + reranker (default) | 0.88 | 0.96 | 1.00 | 0.78 | 0.80 | 0.82 |
| Hybrid + reranker | 0.88 | 0.96 | 0.96 | 0.78 | 0.80 | 0.80 |

## Complementarity of BM25 and dense search (top 5)

| Set | Both found it | Only BM25 | Only dense | Neither |
| --- | --- | --- | --- | --- |
| Fictional documents | 13 | 0 | 0 | 0 |
| Real document (GDPR) | 6 | 0 | 6 | 1 |

## Latency per query (CPU)

| Retrieval | Mean | P95 |
| --- | --- | --- |
| BM25 only | 3 ms | 5 ms |
| Dense only | 56 ms | 73 ms |
| Hybrid (BM25 + dense) | 62 ms | 82 ms |
| Dense + reranker (default) | 1259 ms | 1934 ms |
| Hybrid + reranker | 1932 ms | 2756 ms |
