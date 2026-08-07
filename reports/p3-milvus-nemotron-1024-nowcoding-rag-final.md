# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-v3
- Dense weight: 0.7
- Milvus search multiplier: 30
- Reranker: llm (gpt-5.6-terra)
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: 55
- Reranker degraded calls: 0
- Documents: 28481
- Relations: 7600
- Gold rows total: 180
- Evaluation categories: rag
- Questions scored: 55
- Questions excluded from scoring: 5
- Point-estimate checks passed: no
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Point | CI lower |
|---|---:|:--:|---:|---:|---|---|
| Route accuracy | 1.0000 | 0.9347–1.0000 | 55 | 0.9000 | True | True |
| Permission isolation | 1.0000 | 0.9347–1.0000 | 55 | 1.0000 | True | n/a |
| Base retrieval Recall@3 | 0.8364 | 0.7174–0.9114 | 55 | 0.8500 | False | n/a |
| Base retrieval Top-1 citation accuracy | 0.6727 | 0.5410–0.7819 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.8364 | 0.7174–0.9114 | 55 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.6727 | 0.5410–0.7819 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.3500 | 0.2213–0.5049 | 40 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.8364 | 0.6727 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.7424
- nDCG@3: 0.7476
- Mean answer content recall: 0.4535
- Answer span hit rate, all gold spans: 0.2909 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 8452.48 ms
P95 latency: 13063.83 ms
Index time: 21.9 s
