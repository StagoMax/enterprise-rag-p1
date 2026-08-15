# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-structured-256-48-v1
- Dense weight: 0.7
- Milvus search multiplier: 30
- Milvus search mode: native_rrf
- Fielded search: True
- Query rewrite: True
- Reranker: llm (gpt-5.6-luna)
- Rerank strategy: replace
- Reranker cache mode: record
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: 55
- Reranker degraded calls: 0
- Reranker external calls: 0
- Reranker cache hits: 55
- Reranker deterministic calls: 0
- Reranker HTTP attempts: 0
- Reranker judgement digest: 7f385bc778c9b29b27fd6b7d7fa457569099eb2115beaea777d28fc05cdbe32b
- Documents: 28481
- Relations: 7600
- Gold rows total: 240
- Evaluation categories: rag
- Questions scored: 55
- Questions excluded from scoring: 5
- Point-estimate checks passed: no
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Point | CI lower |
|---|---:|:--:|---:|---:|---|---|
| Route accuracy | 1.0000 | 0.9347–1.0000 | 55 | 0.9000 | True | True |
| Permission isolation | 1.0000 | 0.9347–1.0000 | 55 | 1.0000 | True | n/a |
| Base retrieval Recall@3 | 0.8727 | 0.7598–0.9370 | 55 | 0.8500 | True | n/a |
| Base retrieval Top-1 citation accuracy | 0.6000 | 0.4681–0.7188 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.8727 | 0.7598–0.9370 | 55 | 0.8500 | True | False |
| Semantic RAG Top-1 citation accuracy | 0.6000 | 0.4681–0.7188 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.3171 | 0.1956–0.4698 | 41 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.8727 | 0.6000 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.7273
- nDCG@3: 0.7564
- Mean answer content recall: 0.4660
- Answer span hit rate, all gold spans: 0.2727 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 3877.84 ms
P95 latency: 6243.86 ms
Latency note: includes live reranker latency when reranking is enabled.
Index time: 17.1 s
