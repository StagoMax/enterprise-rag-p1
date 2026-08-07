# P3 Graph RAG Evaluation: nemotron on milvus

- Index version: p3-techqa-28481-nemotron-1024-fielded-v1
- Dense weight: 0.7
- Milvus search multiplier: 30
- Milvus search mode: native_rrf
- Fielded search: True
- Query rewrite: True
- Reranker: llm (deepseek-v4-flash)
- Rerank strategy: weighted_rrf
- Reranker cache mode: replay
- Answer generator: extractive (EvidenceAnswerGenerator)
- Reranker calls: 55
- Reranker degraded calls: 0
- Reranker external calls: 0
- Reranker cache hits: 55
- Reranker deterministic calls: 0
- Reranker HTTP attempts: 0
- Reranker judgement digest: ca0c5e6bd9558170fb66c796a1a54c5dc74f6289408ca032b280d1b6bb578cda
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
| Base retrieval Recall@3 | 0.7636 | 0.6365–0.8563 | 55 | 0.8500 | False | n/a |
| Base retrieval Top-1 citation accuracy | 0.5091 | 0.3808–0.6362 | 55 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.7636 | 0.6365–0.8563 | 55 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.5091 | 0.3808–0.6362 | 55 | 0.9500 | False | False |
| Fitting answer-span hit rate | 0.3500 | 0.2213–0.5049 | 40 | 0.5500 | False | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.7636 | 0.5091 | 55 |
| Exact search | 0.0000 | 0.0000 | 0 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.6242
- nDCG@3: 0.6470
- Mean answer content recall: 0.4540
- Answer span hit rate, all gold spans: 0.2909 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 936.27 ms
P95 latency: 1784.38 ms
Latency note: replay mode uses local cached judgements and is not a deployment latency measurement.
Index time: 17.77 s
