# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-structured-v1
- Dense weight: 0.7
- Milvus search multiplier: 30
- Milvus search mode: native_rrf
- Fielded search: True
- Query rewrite: True
- Reranker: llm (deepseek-v4-flash)
- Rerank strategy: replace
- Reranker cache mode: record
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: 55
- Reranker degraded calls: 0
- Reranker external calls: 55
- Reranker cache hits: 0
- Reranker deterministic calls: 0
- Reranker HTTP attempts: 55
- Reranker judgement digest: 1fb8057a4e8f8834450cf1218b39a6b395505097f924b7411d1f71782d9c5d05
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
| Base retrieval Top-1 citation accuracy | 0.6000 | 0.4681–0.7188 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.8364 | 0.7174–0.9114 | 55 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.6000 | 0.4681–0.7188 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.3500 | 0.2213–0.5049 | 40 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.8364 | 0.6000 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.7030
- nDCG@3: 0.7302
- Mean answer content recall: 0.4495
- Answer span hit rate, all gold spans: 0.2909 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 6134.23 ms
P95 latency: 8433.05 ms
Latency note: includes live reranker latency when reranking is enabled.
Index time: 17.0 s
