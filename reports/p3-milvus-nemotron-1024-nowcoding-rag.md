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
| Base retrieval Recall@3 | 0.8182 | 0.6967–0.8981 | 55 | 0.8500 | False | n/a |
| Base retrieval Top-1 citation accuracy | 0.6909 | 0.5597–0.7972 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.8182 | 0.6967–0.8981 | 55 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.6909 | 0.5597–0.7972 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.2750 | 0.1611–0.4284 | 40 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.8182 | 0.6909 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.7515
- nDCG@3: 0.7507
- Mean answer content recall: 0.4456
- Answer span hit rate, all gold spans: 0.2364 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 8477.16 ms
P95 latency: 13065.76 ms
Index time: 23.69 s
