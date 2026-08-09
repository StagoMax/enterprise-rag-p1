# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-structured-256-48-v1
- Dense weight: 0.7
- Milvus search multiplier: 30
- Milvus search mode: native_rrf
- Fielded search: True
- Query rewrite: True
- Reranker: llm (gpt-5.6-sol)
- Rerank strategy: replace
- Reranker cache mode: record
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: 55
- Reranker degraded calls: 0
- Reranker external calls: 16
- Reranker cache hits: 39
- Reranker deterministic calls: 0
- Reranker HTTP attempts: 17
- Reranker judgement digest: 1beb3935a97c50606bc03c94bea82f85ad337dfd596317faa7a66b7bf479830c
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
| Base retrieval Recall@3 | 0.8909 | 0.7817–0.9490 | 55 | 0.8500 | True | n/a |
| Base retrieval Top-1 citation accuracy | 0.6727 | 0.5410–0.7819 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.8909 | 0.7817–0.9490 | 55 | 0.8500 | True | False |
| Semantic RAG Top-1 citation accuracy | 0.6727 | 0.5410–0.7819 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.3750 | 0.2422–0.5297 | 40 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.8909 | 0.6727 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.7758
- nDCG@3: 0.8056
- Mean answer content recall: 0.4852
- Answer span hit rate, all gold spans: 0.3091 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 4103.91 ms
P95 latency: 34922.51 ms
Latency note: includes live reranker latency when reranking is enabled.
Index time: 16.21 s
