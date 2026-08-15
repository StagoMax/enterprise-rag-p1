# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-structured-256-48-v1
- Dense weight: 0.7
- Milvus search multiplier: 30
- Milvus search mode: native_rrf
- Fielded search: True
- Query rewrite: True
- Reranker: llm (deepseek-v4-flash)
- Rerank strategy: replace
- Reranker cache mode: record
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: 78
- Reranker degraded calls: 0
- Reranker external calls: 65
- Reranker cache hits: 2
- Reranker deterministic calls: 11
- Reranker HTTP attempts: 65
- Reranker judgement digest: 39e0e74f985da96137bcd4e5b453096dc721761516c219c07c6745c226d2a458
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
| Base retrieval Recall@3 | 0.7818 | 0.6563–0.8705 | 55 | 0.8500 | False | n/a |
| Base retrieval Top-1 citation accuracy | 0.5818 | 0.4503–0.7026 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.7818 | 0.6563–0.8705 | 55 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.5818 | 0.4503–0.7026 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.2683 | 0.1569–0.4193 | 41 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.7818 | 0.5818 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.6636
- nDCG@3: 0.6848
- Mean answer content recall: 0.4318
- Answer span hit rate, all gold spans: 0.2364 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 5223.63 ms
P95 latency: 7844.0 ms
Latency note: includes live reranker latency when reranking is enabled.
Index time: 18.92 s
