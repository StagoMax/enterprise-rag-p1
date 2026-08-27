# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-structured-256-48-v1
- Dense weight: 0.7
- Milvus search multiplier: 30
- Milvus search mode: native_rrf
- Fielded search: True
- Query rewrite: True
- Reranker: none (none)
- Rerank strategy: replace
- Reranker cache mode: off
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: None
- Reranker degraded calls: None
- Reranker external calls: None
- Reranker cache hits: None
- Reranker deterministic calls: None
- Reranker HTTP attempts: None
- Reranker judgement digest: None
- Documents: 28481
- Relations: 7600
- Gold rows total: 240
- Evaluation categories: rag
- Questions scored: 115
- Questions excluded from scoring: 5
- Point-estimate checks passed: no
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Point | CI lower |
|---|---:|:--:|---:|---:|---|---|
| Route accuracy | 1.0000 | 0.9677–1.0000 | 115 | 0.9000 | True | True |
| Permission isolation | 1.0000 | 0.9677–1.0000 | 115 | 1.0000 | True | n/a |
| Base retrieval Recall@3 | 0.7130 | 0.6245–0.7878 | 115 | 0.8500 | False | n/a |
| Base retrieval Top-1 citation accuracy | 0.4870 | 0.3975–0.5772 | 115 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.7130 | 0.6245–0.7878 | 115 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.4870 | 0.3975–0.5772 | 115 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.3133 | 0.2236–0.4194 | 83 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.7130 | 0.4870 | 115 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: enabled (limit 20).

## Candidate-to-ranking funnel

| Stage | Hits | Denominator | Conditional rate |
|---|---:|---:|---:|
| Candidate Recall@20 | 107 | 115 | 0.9304 |
| Candidate base Recall@3 | 75 | 107 | 0.7009 |
| Final Recall@3 given candidate hit | 82 | 107 | 0.7664 |
| Candidate base Top-1 | 56 | 107 | 0.5234 |
| Final Top-1 given candidate hit | 56 | 107 | 0.5234 |

- Upstream candidate misses: rag-033, rag-046, rag-066, rag-067, rag-085, rag-092, rag-099, rag-100
- Candidate hits dropped before final Top-3: rag-002, rag-023, rag-026, rag-031, rag-032, rag-034, rag-039, rag-041, rag-045, rag-051, rag-053, rag-056, rag-058, rag-059, rag-065, rag-082, rag-087, rag-089, rag-094, rag-101, rag-104, rag-107, rag-108, rag-111, rag-120
- Rerank rescues versus candidate base Top-3: rag-005, rag-022, rag-028, rag-029, rag-035, rag-069, rag-086
- Rerank regressions versus candidate base Top-3: none
- Final Top-3 is a subset of the candidate pool: True

## Ranking and answer quality

- MRR@3: 0.5870
- nDCG@3: 0.6149
- Mean answer content recall: 0.4337
- Answer span hit rate, all gold spans: 0.2522 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 880.32 ms
P95 latency: 1385.21 ms
Latency note: includes live reranker latency when reranking is enabled.
Index time: 23.15 s
