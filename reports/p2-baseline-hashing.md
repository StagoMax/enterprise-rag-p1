# P2 Graph RAG Evaluation: hashing on memory

- Index version: p2-evaluation-v1
- Dense weight: 0.5
- Milvus search multiplier: 12
- Milvus search mode: separate
- Fielded search: False
- Query rewrite: False
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
- Documents: 1000
- Relations: 307
- Gold rows total: 180
- Evaluation categories: exact_search, graph_rag, graph_unauthorized, no_evidence, rag, tool, unauthorized
- Questions scored: 180
- Questions excluded from scoring: 0
- Point-estimate checks passed: no
- Passed: no

| Metric | Result | 95% CI | n | Threshold | Point | CI lower |
|---|---:|:--:|---:|---:|---|---|
| Route accuracy | 1.0000 | 0.9791–1.0000 | 180 | 0.9000 | True | True |
| Permission isolation | 1.0000 | 0.9791–1.0000 | 180 | 1.0000 | True | n/a |
| Base retrieval Recall@3 | 0.8750 | 0.7850–0.9307 | 80 | 0.8500 | True | n/a |
| Base retrieval Top-1 citation accuracy | 0.7750 | 0.6721–0.8527 | 80 | 0.9500 | False | n/a |
| Semantic RAG Recall@3 | 0.8333 | 0.7197–0.9069 | 60 | 0.8500 | False | False |
| Semantic RAG Top-1 citation accuracy | 0.7000 | 0.5749–0.8010 | 60 | 0.9500 | False | False |
| Graph joint Recall@3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8000 | True | True |
| Graph target Recall@3 | 1.0000 | 0.9124–1.0000 | 40 | 0.8500 | True | True |
| Graph path accuracy | 1.0000 | 0.9124–1.0000 | 40 | 0.9500 | True | False |
| Graph recall gain | 0.4000 | — | — | 0.1500 | True | n/a |
| Graph ACL isolation | 1.0000 | 0.8389–1.0000 | 20 | 1.0000 | True | n/a |
| Refusal accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.9000 | True | False |
| Tool answer accuracy | 1.0000 | 0.8389–1.0000 | 20 | 0.8500 | True | False |
| Fitting answer-span hit rate | 0.6190 | 0.5235–0.7062 | 105 | 0.5500 | True | False |

## Retrieval slices

| Slice | Recall@3 | Top-1 citation | n |
|---|---:|---:|---:|
| Semantic RAG | 0.8333 | 0.7000 | 60 |
| Exact search | 1.0000 | 1.0000 | 20 |

Candidate diagnostics: disabled (limit 20).

## Ranking and answer quality

- MRR@3: 0.9104
- nDCG@3: 0.9174
- Mean answer content recall: 0.6761
- Answer span hit rate, all gold spans: 0.5583 (not gated; falls with gold length, since one excerpt holds 360 chars)

P50 latency: 3662.45 ms
P95 latency: 9383.34 ms
Latency note: includes live reranker latency when reranking is enabled.
Index time: 11.16 s
