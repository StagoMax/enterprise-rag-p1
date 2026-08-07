# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-v3
- Dense weight: 0.7
- Milvus search multiplier: 30
- Reranker: none (none)
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: None
- Reranker degraded calls: None
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
| Base retrieval Recall@3 | 0.6909 | 0.5597–0.7972 | 55 | 0.8500 | False | n/a |
| Base retrieval Top-1 citation accuracy | 0.5818 | 0.4503–0.7026 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.6909 | 0.5597–0.7972 | 55 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.5818 | 0.4503–0.7026 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.3000 | 0.1807–0.4543 | 40 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.6909 | 0.5818 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.6273
- nDCG@3: 0.6365
- Mean answer content recall: 0.4344
- Answer span hit rate, all gold spans: 0.2545 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 707.34 ms
P95 latency: 1123.93 ms
Index time: 21.55 s
