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
- Reranker calls: 79
- Reranker degraded calls: 0
- Reranker external calls: 12
- Reranker cache hits: 55
- Reranker deterministic calls: 12
- Reranker HTTP attempts: 12
- Reranker judgement digest: 513c6dad777a51b90b4ae3d539f71d8c091fd121b77290d0c3f3cb929778fcc1
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
| Base retrieval Recall@3 | 0.7636 | 0.6365–0.8563 | 55 | 0.8500 | False | n/a |
| Base retrieval Top-1 citation accuracy | 0.6000 | 0.4681–0.7188 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.7636 | 0.6365–0.8563 | 55 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.6000 | 0.4681–0.7188 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.2927 | 0.1761–0.4448 | 41 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.7636 | 0.6000 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.6727
- nDCG@3: 0.6820
- Mean answer content recall: 0.4386
- Answer span hit rate, all gold spans: 0.2545 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 4259.58 ms
P95 latency: 12952.35 ms
Latency note: includes live reranker latency when reranking is enabled.
Index time: 17.57 s
